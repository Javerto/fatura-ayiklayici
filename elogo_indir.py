"""eLogo'dan fatura indirme akışı (arayüzden bağımsız)."""

import json
import os
import pathlib
import re
import uuid

from extraction import _duzelt_fatura_no, xml_den_veri_cek
from hatalar import ElogoHatasi, ElogoOturumHatasi

OIDC_ANAHTARI = "oidc.user:https://identityserver-edevlet.elogo.com.tr:portal.customer"
ART_ARDA_HATA_SINIRI = 3
ART_ARDA_YENILEME_SINIRI = 3
_PORTAL_MESAJI = "eLogo yanıtı beklenmedik, portal değişmiş olabilir"


class _IsDurdu(Exception):
    """Kalan faturaları anlamsız kılan hata; mesajı özete gider."""


def _parcalar(metin):
    """Yapıştırılan metnin numaraları: Excel sütunu, virgüllü ya da boşluklu liste."""
    return [p for p in re.split(r"[\s,;]+", str(metin)) if p]


def numaralari_ayristir(metin):
    """Yapıştırılan metin -> (aranacak numaralar, geçersiz numaralar)."""
    gecerli, gecersiz, gorulen = [], [], set()
    for no in _parcalar(metin):
        no, _ = _duzelt_fatura_no(no)
        anahtar = no.casefold()
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        (gecersiz if len(no) > 16 else gecerli).append(no)
    return gecerli, gecersiz


def numara_ozeti(metin):
    """Numara ekranının canlı sayacı; indirmeyle aynı kuralı kullanır."""
    gecerli, gecersiz = numaralari_ayristir(metin)
    return {"aranacak": len(gecerli), "gecersiz": gecersiz,
            "tekrar": len(_parcalar(metin)) - len(gecerli) - len(gecersiz)}


def oturum_coz(ham):
    """sessionStorage kaydı -> (token, customer_id, son_kullanma); giriş bitmediyse None.

    Müşteri alanı beklenen şekilde değilse tahmin yürütülmez: çok firmalı
    hesapta alanın şekli ölçülmedi, yanlış firmada aramak "bulunamadı" der.
    """
    try:
        veri = json.loads(ham)
    except (TypeError, ValueError):
        return None
    token = veri.get("access_token") if isinstance(veri, dict) else None
    if not token:
        return None
    try:
        musteri = json.loads(veri["profile"]["assignedCustomers"])
        customer_id = str(uuid.UUID(musteri["CustomerId"]))
        son_kullanma = veri["expires_at"]
        if isinstance(son_kullanma, bool) or not isinstance(son_kullanma, (int, float)):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        # `from None`: JSON hatasının `doc` alanı oturum verisini taşır.
        raise ElogoHatasi("eLogo hesap bilgisi beklenen biçimde değil. "
                          "Birden çok firmalı hesaplar henüz desteklenmiyor.") from None
    return token, customer_id, son_kullanma


class _Oturum:
    """Geçerli istemciyi tutar; oturum düşünce yeniden giriş ister ve çağrıyı tekrarlar."""

    def __init__(self, istemci_al, log_q):
        self._al = istemci_al
        self._log_q = log_q
        self._istemci = None
        self._yenileme = 0

    def cagir(self, islem):
        while True:
            if self._istemci is None:
                self._istemci = self._giris()
            try:
                sonuc = islem(self._istemci)
            except ElogoOturumHatasi:
                self._istemci = None
                self._yenileme += 1
                if self._yenileme >= ART_ARDA_YENILEME_SINIRI:
                    raise _IsDurdu("eLogo oturumu art arda düştü, iş durduruldu.") from None
                self._log_q.put(("warn", "eLogo oturumu sona erdi, tekrar giriş yap."))
                continue
            self._yenileme = 0
            return sonuc

    def _giris(self):
        try:
            istemci = self._al()
        except ElogoHatasi as e:
            raise _IsDurdu(str(e)) from None
        if istemci is None:
            raise _IsDurdu("eLogo girişi tamamlanmadı.")
        return istemci


def _satir(log_q, no, durum, mesaj):
    log_q.put(("elogo_satir", {"no": no, "durum": durum, "mesaj": mesaj}))


def _xml_vkn(yol):
    try:
        vkn = xml_den_veri_cek(str(yol), None).get("vkn")
    except Exception:
        return None
    return vkn if isinstance(vkn, str) and re.fullmatch(r"\d{10,11}", vkn) else None


def _eslesme_indir(no, sira, fatura, klasor, oturum, ozet, log_q):
    """Tek eşleşmeyi işler; art arda hata sayacını sıfırlıyorsa True döner."""
    invoice_id = fatura.get("InvoiceId")
    if not isinstance(invoice_id, str) or not invoice_id:
        raise ElogoHatasi("Fatura kimliği geçersiz.")
    # Portal değeri dosya yoluna girer: klasör dışına yazamasın.
    portal_no = fatura.get("InvoiceNumber")
    if not isinstance(portal_no, str) or not re.fullmatch(r"[A-Za-z0-9]+", portal_no):
        ozet["gecersiz"].append(no)
        _satir(log_q, no, "gecersiz", "Portalın döndürdüğü numara dosya adı olamaz.")
        return False

    gonderen = fatura.get("Sender")
    vkn = gonderen.get("VKN_TCKN") if isinstance(gonderen, dict) else None
    if not (isinstance(vkn, str) and re.fullmatch(r"\d{10,11}", vkn)):
        vkn = None

    def atla(ad):
        ozet["atlanan"].append(no)
        _satir(log_q, no, "atlandi", f"{ad} klasörde zaten var.")
        return True

    ad = portal_no if sira == 0 else f"{portal_no}_{vkn}" if vkn else None
    if ad and (klasor / f"{ad}.xml").exists():
        return atla(f"{ad}.xml")

    veri = oturum.cagir(lambda istemci: istemci.xml_indir(invoice_id))
    if not veri:
        raise ElogoHatasi("eLogo boş XML döndürdü.")

    # Yarım dosya inmiş fatura gibi görünmesin; `.tmp` klasör taramasına da girmez.
    gecici = klasor / f"{portal_no}_{sira}.xml.tmp"
    try:
        gecici.write_bytes(veri)
        if ad is None:
            kimlik = re.sub(r"[^A-Za-z0-9-]", "", invoice_id)[:64] or "kimliksiz"
            ad = f"{portal_no}_{_xml_vkn(gecici) or kimlik}"
            if (klasor / f"{ad}.xml").exists():
                return atla(f"{ad}.xml")
        # `replace` değil: indirme sürerken aynı adla gelen dosya ezilmesin.
        # Windows'ta `rename` hedef varsa FileExistsError verir.
        try:
            os.rename(gecici, klasor / f"{ad}.xml")
        except FileExistsError:
            return atla(f"{ad}.xml")
    finally:
        gecici.unlink(missing_ok=True)

    ozet["indirilen"].append(no)
    _satir(log_q, no, "indirildi", f"{ad}.xml")
    return True


def _calistir(nolar, klasor, oturum, ozet, tamam, log_q, stop_event):
    try:
        bulunan = oturum.cagir(lambda istemci: istemci.fatura_bul(nolar))
    except ElogoHatasi as e:
        raise _IsDurdu(f"{_PORTAL_MESAJI}: {e}") from None

    # Yalnız portaldan yanıt alınan indirme sıfırlar: "bulunamadı" ve "geçersiz"
    # portala istek atmaz, aradaki olmaları hataları ardışık olmaktan çıkarmaz.
    ardisik_hata = 0
    for sayac, no in enumerate(nolar, 1):
        eslesmeler = bulunan.get(no) or []
        if not eslesmeler:
            ozet["bulunamayan"].append(no)
            _satir(log_q, no, "bulunamadi", "eLogo'da bulunamadı.")
        elif len(eslesmeler) > 1:
            ozet["coklu"].append(no)
        # Sıra sabit olmalı: portal sırayı değiştirirse devam ederken ilk
        # faturanın adı başkasına verilir, gerçek ilk fatura "var" sanılıp atlanırdı.
        for sira, fatura in enumerate(sorted(eslesmeler, key=lambda f: str(f.get("InvoiceId")))):
            if stop_event.is_set():
                return
            try:
                if _eslesme_indir(no, sira, fatura, klasor, oturum, ozet, log_q):
                    ardisik_hata = 0
            except ElogoHatasi as e:
                ardisik_hata += 1
                ozet["hatali"].append(no)
                log_q.put(("warn", f"{_PORTAL_MESAJI}: {e}"))
                _satir(log_q, no, "hata", str(e))
                if ardisik_hata >= ART_ARDA_HATA_SINIRI:
                    tamam.add(no)
                    raise _IsDurdu("Art arda 3 eLogo hatası oluştu, iş durduruldu.") from None
            except OSError as e:
                raise _IsDurdu(f"XML klasöre yazılamadı: {e}") from None
        tamam.add(no)
        log_q.put(("progress", [sayac, len(nolar)]))


def indir(nolar, gecersiz, klasor, istemci_al, log_q, stop_event):
    """Numaraları indirir ve özeti döndürür; son olay her koşulda ("elogo_ozet", ozet)."""
    ozet = {"indirilen": [], "atlanan": [], "bulunamayan": [], "gecersiz": list(gecersiz),
            "hatali": [], "coklu": [], "indirilmedi": [], "hata": None, "durduruldu": False}
    tamam = set()
    try:
        for no in gecersiz:
            _satir(log_q, no, "gecersiz", "16 karakterden uzun.")
        if nolar:
            log_q.put(("progress", [0, len(nolar)]))
            _calistir(nolar, pathlib.Path(klasor), _Oturum(istemci_al, log_q),
                      ozet, tamam, log_q, stop_event)
    except _IsDurdu as e:
        ozet["hata"] = str(e)
    except Exception as e:
        # Yalnız tip adı: istisna metni yanıt gövdesi ya da oturum verisi taşıyabilir.
        ozet["hata"] = f"Beklenmedik hata: {type(e).__name__}"
    ozet["durduruldu"] = stop_event.is_set()
    if ozet["durduruldu"]:
        ozet["hata"] = None     # Durdur'un yarıda kestiği giriş hata değil
    ozet["indirilmedi"] = [no for no in nolar if no not in tamam]
    log_q.put(("elogo_ozet", ozet))
    return ozet
