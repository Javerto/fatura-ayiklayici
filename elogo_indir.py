"""eLogo'dan fatura indirme akışı (arayüzden bağımsız)."""

import json
import os
import pathlib
import re
import uuid

from extraction import _duzelt_fatura_no, xml_den_veri_cek
from hatalar import ElogoHatasi, ElogoOturumHatasi


def numaralari_ayristir(metin):
    gecersiz, gecerli, gorulen = [], [], set()
    for satir in str(metin).splitlines():
        no = satir.strip()
        if not no:
            continue
        no, _ = _duzelt_fatura_no(no)
        if len(no) > 16:
            gecersiz.append(no)
            continue
        anahtar = no.casefold()
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            gecerli.append(no)
    return gecerli, gecersiz


def oturum_coz(ham):
    try:
        veri = json.loads(ham)
        token = veri.get("access_token")
        if not token:
            return None
        profil = veri["profile"]
        atanmis = json.loads(profil["assignedCustomers"])
        if not isinstance(atanmis, dict):
            raise ValueError
        customer_id = atanmis.get("CustomerId")
        uuid.UUID(str(customer_id))
        return token, str(customer_id), veri["expires_at"]
    except (json.JSONDecodeError, TypeError, KeyError, AttributeError,
            ValueError, OverflowError):
        if "token" not in locals() or not token:
            return None
        raise ElogoHatasi("eLogo müşteri bilgisi beklenen biçimde değil; tek müşteri hesabıyla tekrar giriş yapın.")


def _ozet():
    return {"indirilen": [], "atlanan": [], "bulunamayan": [],
            "gecersiz": [], "hatali": [], "coklu": [],
            "indirilmedi": [], "hata": None, "durduruldu": False}


def _olay(log_q, tag, veri):
    if log_q is not None:
        log_q.put((tag, veri))


def _guvenli_parca(deger):
    return re.sub(r"[^A-Za-z0-9_-]", "", str(deger)) or "bilinmeyen"


def indir(nolar, gecersiz, klasor, istemci_al, log_q, stop_event):
    ozet = _ozet()
    ozet["gecersiz"].extend(gecersiz)
    for no in gecersiz:
        _olay(log_q, "elogo_satir", {"no": no, "durum": "gecersiz", "mesaj": "Numara çok uzun."})
    if not nolar:
        _olay(log_q, "elogo_ozet", ozet)
        return ozet

    istemci = None
    arama = {}
    hata_sayaci = 0
    yenileme = 0
    try:
        istemci = istemci_al()
        if istemci is None:
            ozet["hata"] = "eLogo girişinden vazgeçildi."
            ozet["indirilmedi"].extend(nolar)
            return ozet
        while True:
            try:
                arama = istemci.fatura_bul(nolar)
                break
            except ElogoOturumHatasi:
                yenileme += 1
                _olay(log_q, "warn", "eLogo oturumu sona erdi, tekrar giriş yapın")
                if yenileme >= 3 or (istemci := istemci_al()) is None:
                    ozet["hata"] = "eLogo oturumu yenilenemedi."
                    ozet["indirilmedi"].extend(nolar)
                    return ozet
            except ElogoHatasi as e:
                ozet["hata"] = str(e)
                ozet["indirilmedi"].extend(nolar)
                return ozet

        toplam = sum(len(arama.get(no, [])) for no in nolar)
        _olay(log_q, "progress", [0, toplam or len(nolar)])
        ilerleme = 0
        for no in nolar:
            if stop_event.is_set():
                ozet["durduruldu"] = True
                break
            eslesmeler = list(arama.get(no, []))
            if not eslesmeler:
                ozet["bulunamayan"].append(no)
                _olay(log_q, "elogo_satir", {"no": no, "durum": "bulunamadi", "mesaj": "Fatura bulunamadı."})
                ilerleme += 1
                _olay(log_q, "progress", [ilerleme, toplam or len(nolar)])
                continue
            if len(eslesmeler) > 1:
                ozet["coklu"].append(no)
            for sira, fatura in enumerate(sorted(eslesmeler, key=lambda x: str(x.get("InvoiceId", "")))):
                if stop_event.is_set():
                    ozet["durduruldu"] = True
                    break
                try:
                    _indir_eslesme(no, sira, fatura, klasor, istemci, istemci_al,
                                   ozet, log_q, stop_event)
                    hata_sayaci = 0
                except ElogoOturumHatasi:
                    yenileme += 1
                    _olay(log_q, "warn", "eLogo oturumu sona erdi, tekrar giriş yapın")
                    if yenileme >= 3 or (istemci := istemci_al()) is None:
                        ozet["hata"] = "eLogo oturumu yenilenemedi."
                        ozet["indirilmedi"].extend(nolar[nolar.index(no):])
                        return ozet
                    # Aynı eşleşme yeniden denenir.
                    try:
                        _indir_eslesme(no, sira, fatura, klasor, istemci, istemci_al,
                                       ozet, log_q, stop_event)
                        yenileme = 0
                        hata_sayaci = 0
                    except ElogoOturumHatasi:
                        yenileme += 1
                        if yenileme >= 3:
                            ozet["hata"] = "eLogo oturumu yenilenemedi."
                            ozet["indirilmedi"].extend(nolar[nolar.index(no):])
                            return ozet
                        continue
                except ElogoHatasi as e:
                    hata_sayaci += 1
                    ozet["hatali"].append(no)
                    _olay(log_q, "warn", f"eLogo yanıtı beklenmedik, portal değişmiş olabilir: {e}")
                    _olay(log_q, "elogo_satir", {"no": no, "durum": "hata", "mesaj": str(e)})
                    if hata_sayaci >= 3:
                        ozet["hata"] = "Art arda üç eLogo hatası oluştu."
                        ozet["indirilmedi"].extend(nolar[nolar.index(no) + 1:])
                        return ozet
                except OSError:
                    ozet["hata"] = "eLogo XML dosyası yazılamadı."
                    ozet["indirilmedi"].extend(nolar[nolar.index(no):])
                    return ozet
                ilerleme += 1
                _olay(log_q, "progress", [ilerleme, toplam or len(nolar)])
    except Exception as e:
        ozet["hata"] = type(e).__name__
        ozet["indirilmedi"].extend([n for n in nolar if n not in ozet["indirilen"] and n not in ozet["atlanan"] and n not in ozet["bulunamayan"]])
    finally:
        if stop_event.is_set():
            ozet["durduruldu"] = True
            for no in nolar:
                if no not in ozet["indirilen"] and no not in ozet["atlanan"] and no not in ozet["bulunamayan"] and no not in ozet["hatali"] and no not in ozet["indirilmedi"]:
                    ozet["indirilmedi"].append(no)
        _olay(log_q, "elogo_ozet", ozet)
    return ozet


def _indir_eslesme(no, sira, fatura, klasor, istemci, istemci_al, ozet, log_q, stop_event):
    invoice_id = fatura.get("InvoiceId")
    if not isinstance(invoice_id, str):
        raise ElogoHatasi("eLogo InvoiceId değeri geçersiz.")
    portal_no = fatura.get("InvoiceNumber")
    if not isinstance(portal_no, str) or not re.fullmatch(r"[A-Za-z0-9]+", portal_no):
        ozet["gecersiz"].append(no)
        _olay(log_q, "elogo_satir", {"no": no, "durum": "gecersiz", "mesaj": "Portal fatura numarası güvenli değil."})
        return
    sender = fatura.get("Sender") or {}
    vkn = sender.get("VKN_TCKN") if isinstance(sender, dict) else None
    if not isinstance(vkn, str) or not re.fullmatch(r"\d{10,11}", vkn):
        vkn = None
    ad = portal_no if sira == 0 else f"{portal_no}_{vkn or _guvenli_parca(invoice_id)}"
    hedef = pathlib.Path(klasor) / f"{ad}.xml"
    klasor_yol = pathlib.Path(klasor).resolve()
    if hedef.resolve().parent != klasor_yol:
        raise ElogoHatasi("eLogo dosya adı güvenli değil.")
    if hedef.exists():
        ozet["atlanan"].append(no)
        _olay(log_q, "elogo_satir", {"no": no, "durum": "atlandi", "mesaj": "Dosya zaten var."})
        return
    veri = istemci.xml_indir(invoice_id)
    if not veri:
        raise ElogoHatasi("eLogo boş XML döndürdü.")
    gecici = hedef.with_name(hedef.name + ".tmp")
    try:
        gecici.write_bytes(veri)
        if vkn is None:
            xml_vkn = xml_den_veri_cek(str(gecici), None).get("vkn")
            if isinstance(xml_vkn, str) and re.fullmatch(r"\d{10,11}", xml_vkn):
                vkn = xml_vkn
        if sira > 0 and not f"_{vkn or _guvenli_parca(invoice_id)}" in hedef.name:
            yeni = hedef.with_name(f"{portal_no}_{vkn or _guvenli_parca(invoice_id)}.xml")
            if yeni.exists():
                ozet["atlanan"].append(no)
                return
            hedef = yeni
        os.replace(gecici, hedef)
    except OSError:
        try:
            gecici.unlink()
        except OSError:
            pass
        raise
    finally:
        if gecici.exists():
            gecici.unlink()
    ozet["indirilen"].append(no)
    _olay(log_q, "elogo_satir", {"no": no, "durum": "indirildi", "mesaj": hedef.name})
