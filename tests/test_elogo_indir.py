import json
import pathlib
import queue
import threading
import time

import pytest

import elogo_indir
from elogo_indir import indir, numaralari_ayristir, oturum_coz
from hatalar import ElogoHatasi, ElogoOturumHatasi

ORNEK_XML = pathlib.Path("tests/fixtures/ornek_fatura.xml").read_bytes()
MUSTERI = "12345678-1234-1234-1234-123456789012"


def oge(kimlik, no="A1", vkn="1234567890"):
    o = {"InvoiceId": kimlik, "InvoiceNumber": no}
    if vkn is not None:
        o["Sender"] = {"VKN_TCKN": vkn}
    return o


class Sahte:
    """`bulunan`: numara -> öğeler. `hatalar`: kimlik -> sırayla fırlatılacak istisnalar."""

    def __init__(self, bulunan=None, hatalar=None, bul_hatasi=None):
        self.bulunan, self.hatalar, self.bul_hatasi = bulunan or {}, hatalar or {}, bul_hatasi
        self.indirilen = []

    def fatura_bul(self, nolar):
        if self.bul_hatasi:
            raise self.bul_hatasi.pop(0) if isinstance(self.bul_hatasi, list) else self.bul_hatasi
        return {no: self.bulunan.get(no, []) for no in nolar}

    def xml_indir(self, kimlik):
        self.indirilen.append(kimlik)
        kuyruk = self.hatalar.get(kimlik)
        if kuyruk:
            raise kuyruk.pop(0)
        return ORNEK_XML


def calistir(tmp_path, nolar, istemci, gecersiz=(), dur=None):
    q = queue.Queue()
    al = istemci if callable(istemci) else lambda: istemci
    ozet = indir(list(nolar), list(gecersiz), str(tmp_path), al, q, dur or threading.Event())
    olaylar = []
    while not q.empty():
        olaylar.append(q.get_nowait())
    assert olaylar[-1] == ("elogo_ozet", ozet)
    assert [t for t, _ in olaylar].count("elogo_ozet") == 1
    return ozet, olaylar


def dosyalar(klasor):
    return sorted(p.name for p in klasor.iterdir())


# ── Ayrıştırma ───────────────────────────────────────────────────────

def test_numaralar_kirpilir_tekillenir_uzun_olan_gecersiz():
    gecerli, gecersiz = numaralari_ayristir(" AB\r\nab\n\n   \nCD\n" + "X" * 17)
    assert gecerli == ["AB", "CD"]
    assert gecersiz == ["X" * 17]


def test_duzeltme_uzunluk_kontrolunden_once_uygulanir():
    # Modelin eklediği baştaki sıfırı düzelten aynı kural: 17 → 16 karakter.
    assert numaralari_ayristir("GIB20240000000001") == (["GIB2024000000001"], [])


# ── Oturum ───────────────────────────────────────────────────────────

def ham(**ust):
    return json.dumps({"access_token": "gizli", "expires_at": 12,
                       "profile": {"assignedCustomers": json.dumps({"CustomerId": MUSTERI})},
                       **ust})


def test_oturum_gercek_sekil():
    assert oturum_coz(ham()) == ("gizli", MUSTERI, 12)


@pytest.mark.parametrize("deger", [None, "", "bozuk", "[]", '{"profile": {}}', ham(access_token="")])
def test_giris_bitmediyse_none(deger):
    assert oturum_coz(deger) is None


@pytest.mark.parametrize("ust", [
    {"profile": {}},
    {"profile": {"assignedCustomers": "bozuk"}},
    {"profile": {"assignedCustomers": json.dumps([{"CustomerId": MUSTERI}])}},
    {"profile": {"assignedCustomers": json.dumps({"CustomerId": "guid-degil"})}},
    {"expires_at": "yarin"},
    {"expires_at": True},
])
def test_hesap_bilgisi_beklenmedikse_tahmin_yurutulmez(ust):
    with pytest.raises(ElogoHatasi) as e:
        oturum_coz(ham(**ust))
    assert "gizli" not in str(e.value)
    assert e.value.__suppress_context__      # JSON hatası oturum verisi taşır


# ── Adlandırma ───────────────────────────────────────────────────────

def test_dosya_adi_portaldaki_numaradan_gelir(tmp_path):
    s = Sahte({"a1": [oge("1", no="A1")]})
    ozet, _ = calistir(tmp_path, ["a1"], s)
    assert dosyalar(tmp_path) == ["A1.xml"]
    assert ozet["indirilen"] == ["a1"]
    assert (tmp_path / "A1.xml").read_bytes() == ORNEK_XML


def test_coklu_eslesmede_ilki_sade_digerleri_vkn_ile(tmp_path):
    s = Sahte({"A1": [oge("1", vkn="1111111111"), oge("2", vkn="2222222222")]})
    ozet, _ = calistir(tmp_path, ["A1"], s)
    assert dosyalar(tmp_path) == ["A1.xml", "A1_2222222222.xml"]
    assert ozet["coklu"] == ["A1"]


def test_portal_sirasi_degisse_de_ayni_fatura_ayni_adi_alir(tmp_path):
    a, b = oge("1", vkn="1111111111"), oge("2", vkn="2222222222")
    calistir(tmp_path, ["A1"], Sahte({"A1": [b, a]}))
    assert dosyalar(tmp_path) == ["A1.xml", "A1_2222222222.xml"]
    s = Sahte({"A1": [a, b]})
    ozet, _ = calistir(tmp_path, ["A1"], s)     # devam: ikisi de var
    assert s.indirilen == []
    assert ozet["atlanan"] == ["A1", "A1"]


def test_vkn_sender_yoksa_xmlden_o_da_yoksa_kimlikten(tmp_path, monkeypatch):
    s = Sahte({"A1": [oge("1", vkn=None), oge("2", vkn=None)]})
    calistir(tmp_path, ["A1"], s)
    ikinci = [d for d in dosyalar(tmp_path) if d != "A1.xml"]
    assert len(ikinci) == 1 and ikinci[0][3:-4].isdigit()      # fixture'ın VKN'si

    baska = tmp_path / "b"
    baska.mkdir()
    monkeypatch.setattr(elogo_indir, "xml_den_veri_cek", lambda *a: {"vkn": "../kotu"})
    calistir(baska, ["A1"], Sahte({"A1": [oge("1", vkn=None), oge("x/../2", vkn=None)]}))
    assert dosyalar(baska) == ["A1.xml", "A1_x2.xml"]


def test_xml_cozulemese_de_is_durmaz(tmp_path, monkeypatch):
    def patla(*a):
        raise ValueError("bozuk xml")
    monkeypatch.setattr(elogo_indir, "xml_den_veri_cek", patla)
    ozet, _ = calistir(tmp_path, ["A1"], Sahte({"A1": [oge("1", vkn=None), oge("2", vkn=None)]}))
    assert ozet["hata"] is None
    assert dosyalar(tmp_path) == ["A1.xml", "A1_2.xml"]


@pytest.mark.parametrize("kotu", ["..\\..\\x", "../x", "C:\\x", "a.b", "", None, 5])
def test_portal_numarasi_klasor_disina_yazamaz(tmp_path, kotu):
    hedef = tmp_path / "hedef"
    hedef.mkdir()
    s = Sahte({"A1": [oge("1", no=kotu)]})
    ozet, _ = calistir(hedef, ["A1"], s)
    assert s.indirilen == []
    assert ozet["gecersiz"] == ["A1"]
    assert dosyalar(tmp_path) == ["hedef"] and dosyalar(hedef) == []


def test_kotu_vkn_yola_girmez(tmp_path):
    s = Sahte({"A1": [oge("1"), oge("2", vkn="..\\x")]})
    ozet, _ = calistir(tmp_path, ["A1"], s)
    assert ozet["hata"] is None
    assert len(dosyalar(tmp_path)) == 2
    assert all(".." not in d for d in dosyalar(tmp_path))


# ── Atlama, bulunamama, ilerleme ─────────────────────────────────────

def test_var_olan_dosya_indirilmez(tmp_path):
    (tmp_path / "A1.xml").write_bytes(b"eski")
    s = Sahte({"A1": [oge("1")]})
    ozet, olaylar = calistir(tmp_path, ["A1"], s)
    assert s.indirilen == []
    assert ozet["atlanan"] == ["A1"] and ozet["indirilen"] == []
    assert (tmp_path / "A1.xml").read_bytes() == b"eski"
    assert ("elogo_satir", {"no": "A1", "durum": "atlandi",
                            "mesaj": "A1.xml klasörde zaten var."}) in olaylar


def test_ilerleme_toplami_asmaz_ve_tamamlanir(tmp_path):
    s = Sahte({"A1": [oge("1"), oge("2", vkn="2222222222")]})
    _, olaylar = calistir(tmp_path, ["A1", "B2", "C3"], s)
    ilerleme = [d for t, d in olaylar if t == "progress"]
    assert ilerleme == [[0, 3], [1, 3], [2, 3], [3, 3]]


def test_gecerli_numara_yoksa_giris_acilmaz(tmp_path):
    def al():
        pytest.fail("giriş açılmamalıydı")
    ozet, _ = calistir(tmp_path, [], al, gecersiz=["X" * 17])
    assert ozet["gecersiz"] == ["X" * 17] and ozet["hata"] is None


# ── Art arda hata ────────────────────────────────────────────────────

def test_uc_ardisik_hatada_durur_kalanlar_indirilmedi(tmp_path):
    bulunan = {n: [oge(n, no=n)] for n in "ABCDE"}
    s = Sahte(bulunan, {n: [ElogoHatasi("x")] for n in "ABC"})
    ozet, _ = calistir(tmp_path, list("ABCDE"), s)
    assert ozet["hatali"] == list("ABC")
    assert ozet["indirilmedi"] == list("DE")
    assert "Art arda 3" in ozet["hata"]
    assert s.indirilen == list("ABC")


def test_basari_ve_atlama_sayaci_sifirlar(tmp_path):
    (tmp_path / "C.xml").write_bytes(b"var")
    bulunan = {n: [oge(n, no=n)] for n in "ABCDEFG"}
    s = Sahte(bulunan, {n: [ElogoHatasi("x")] for n in "ABDE"})
    ozet, _ = calistir(tmp_path, list("ABCDEFG"), s)     # A B (atla C) D E F G
    assert ozet["hata"] is None
    assert ozet["hatali"] == list("ABDE")
    assert ozet["indirilen"] == list("FG")


def test_liste_cagrisi_hatasi_isi_durdurur(tmp_path):
    ozet, _ = calistir(tmp_path, ["A", "B"], Sahte(bul_hatasi=ElogoHatasi("x")))
    assert "portal değişmiş" in ozet["hata"]
    assert ozet["indirilmedi"] == ["A", "B"]


# ── Oturum yenileme ──────────────────────────────────────────────────

def test_oturum_duserse_ayni_fatura_yeni_istemciyle_denenir(tmp_path):
    bulunan = {"A": [oge("a", no="A")], "B": [oge("b", no="B")]}
    eski = Sahte(bulunan, {"b": [ElogoOturumHatasi("x")]})
    yeni = Sahte(bulunan)
    sira = [eski, yeni]
    ozet, olaylar = calistir(tmp_path, ["A", "B"], lambda: sira.pop(0))
    assert yeni.indirilen == ["b"]
    assert ozet["indirilen"] == ["A", "B"] and ozet["hata"] is None
    assert ("warn", "eLogo oturumu sona erdi, tekrar giriş yap.") in olaylar


def test_liste_cagrisinda_oturum_duserse_tekrar_denenir(tmp_path):
    bulunan = {"A": [oge("a", no="A")]}
    sira = [Sahte(bul_hatasi=ElogoOturumHatasi("x")), Sahte(bulunan)]
    ozet, _ = calistir(tmp_path, ["A"], lambda: sira.pop(0))
    assert ozet["indirilen"] == ["A"]


def test_yenileme_sonrasi_fatura_hatasi_sayaca_girer(tmp_path):
    """Yenileme sonrası gelen hata işi kestirmemeli, sıradan fatura hatası olmalı."""
    bulunan = {"A": [oge("a", no="A")], "B": [oge("b", no="B")]}
    eski = Sahte(bulunan, {"a": [ElogoOturumHatasi("x")]})
    yeni = Sahte(bulunan, {"a": [ElogoHatasi("y")]})
    sira = [eski, yeni]
    ozet, _ = calistir(tmp_path, ["A", "B"], lambda: sira.pop(0))
    assert ozet["hatali"] == ["A"] and ozet["indirilen"] == ["B"] and ozet["hata"] is None


def test_girisden_vazgecilirse_durur_kalanlar_indirilmedi(tmp_path):
    bulunan = {"A": [oge("a", no="A")], "B": [oge("b", no="B")], "C": [oge("c", no="C")]}
    eski = Sahte(bulunan, {"b": [ElogoOturumHatasi("x")]})
    sira = [eski, None]
    ozet, _ = calistir(tmp_path, list("ABC"), lambda: sira.pop(0))
    assert ozet["indirilen"] == ["A"]
    assert ozet["indirilmedi"] == ["B", "C"]
    assert "giriş" in ozet["hata"]


def test_ilk_giristen_vazgecilirse_hic_arama_yapilmaz(tmp_path):
    ozet, _ = calistir(tmp_path, ["A"], lambda: None)
    assert ozet["indirilmedi"] == ["A"]


def test_hesap_bilgisi_hatasinin_mesaji_ozete_gider(tmp_path):
    def al():
        raise ElogoHatasi("Birden çok firmalı hesaplar henüz desteklenmiyor.")
    ozet, _ = calistir(tmp_path, ["A"], al)
    assert ozet["hata"] == "Birden çok firmalı hesaplar henüz desteklenmiyor."


def test_surekli_dusen_oturum_sonsuz_donguye_girmez(tmp_path):
    bulunan = {"A": [oge("a", no="A")]}
    verilen = []

    def al():
        verilen.append(1)
        return Sahte(bulunan, {"a": [ElogoOturumHatasi("x")]})
    ozet, _ = calistir(tmp_path, ["A"], al)
    assert len(verilen) == 3
    assert "art arda" in ozet["hata"]
    assert ozet["indirilmedi"] == ["A"]


def test_basarili_indirme_yenileme_sayacini_sifirlar(tmp_path):
    """60 dk'lık token: uzun işte aralıklı yenilemeler işi durdurmamalı."""
    nolar = list("ABCDEF")
    bulunan = {n: [oge(n, no=n)] for n in nolar}
    istemciler = []

    def al():
        # Her istemci yalnız ilk faturasını indirir, sonra oturumu düşer.
        s = Sahte(bulunan)
        kalan = {"hak": 1}
        gercek = s.xml_indir

        def xml_indir(kimlik):
            if kalan["hak"] == 0:
                raise ElogoOturumHatasi("x")
            kalan["hak"] -= 1
            return gercek(kimlik)
        s.xml_indir = xml_indir
        istemciler.append(s)
        return s
    ozet, _ = calistir(tmp_path, nolar, al)
    assert ozet["hata"] is None and ozet["indirilen"] == nolar
    assert len(istemciler) == 6


# ── Durdur ve yazma ──────────────────────────────────────────────────

def test_durdur_inenleri_birakir_kalanlari_listeler(tmp_path):
    dur = threading.Event()
    bulunan = {n: [oge(n, no=n)] for n in "ABC"}

    class Duran(Sahte):
        def xml_indir(self, kimlik):
            dur.set()
            return super().xml_indir(kimlik)
    ozet, _ = calistir(tmp_path, list("ABC"), Duran(bulunan), dur=dur)
    assert dosyalar(tmp_path) == ["A.xml"]
    assert ozet["durduruldu"] and ozet["hata"] is None
    assert ozet["indirilmedi"] == ["B", "C"]


def test_giris_durdurulursa_hata_gosterilmez(tmp_path):
    dur = threading.Event()

    def al():
        dur.set()
        return None
    ozet, _ = calistir(tmp_path, ["A"], al, dur=dur)
    assert ozet["durduruldu"] and ozet["hata"] is None


def test_yazma_hatasi_isi_durdurur_tmp_kalmaz(tmp_path, monkeypatch):
    def patla(*a):
        raise PermissionError("kilitli")
    monkeypatch.setattr(elogo_indir.os, "rename", patla)
    bulunan = {n: [oge(n, no=n)] for n in "AB"}
    ozet, _ = calistir(tmp_path, ["A", "B"], Sahte(bulunan))
    assert "yazılamadı" in ozet["hata"]
    assert ozet["indirilmedi"] == ["A", "B"]
    assert dosyalar(tmp_path) == []


def test_indirme_sirasinda_gelen_dosya_ezilmez(tmp_path):
    class Yarisan(Sahte):
        def xml_indir(self, kimlik):
            (tmp_path / "A1.xml").write_bytes(b"baskasi")
            return super().xml_indir(kimlik)
    ozet, _ = calistir(tmp_path, ["A1"], Yarisan({"A1": [oge("1")]}))
    assert (tmp_path / "A1.xml").read_bytes() == b"baskasi"
    assert ozet["atlanan"] == ["A1"] and ozet["indirilen"] == []
    assert dosyalar(tmp_path) == ["A1.xml"]


def test_bos_xml_fatura_hatasidir(tmp_path):
    class Bos(Sahte):
        def xml_indir(self, kimlik):
            return b""
    ozet, _ = calistir(tmp_path, ["A"], Bos({"A": [oge("a", no="A")]}))
    assert ozet["hatali"] == ["A"] and dosyalar(tmp_path) == []


def test_beklenmeyen_hatada_mesaj_sizmaz(tmp_path):
    class Patlayan(Sahte):
        def fatura_bul(self, nolar):
            raise RuntimeError("gizli-token")
    ozet, olaylar = calistir(tmp_path, ["A"], Patlayan())
    assert ozet["hata"] == "Beklenmedik hata: RuntimeError"
    assert "gizli-token" not in json.dumps(olaylar, ensure_ascii=False)


# ── Api ──────────────────────────────────────────────────────────────

class _KapanisOlayi:
    def __init__(self):
        self.isleyici = None

    def __iadd__(self, isleyici):
        self.isleyici = isleyici
        return self


class SahtePencere:
    def __init__(self, cevaplar=()):
        self.cevaplar = list(cevaplar)
        self.kapatildi = threading.Event()
        self.events = type("O", (), {})()
        self.events.closed = _KapanisOlayi()

    def evaluate_js(self, kod):
        assert elogo_indir.OIDC_ANAHTARI in kod
        return self.cevaplar.pop(0) if self.cevaplar else None

    def destroy(self):
        self.kapatildi.set()


@pytest.fixture
def api(tmp_path, monkeypatch):
    import api as api_modulu
    a = api_modulu.Api(kok=tmp_path)
    gercek_wait = a._stop_event.wait
    monkeypatch.setattr(a._stop_event, "wait", lambda t=None: gercek_wait(0.01))
    return a


def api_modulu():
    import api as modul
    return modul


def pencere_ac(monkeypatch, pencere):
    import api as api_modulu
    cagri = {}

    def olustur(baslik, adres, **kw):
        cagri.update(adres=adres, **kw)
        return pencere
    monkeypatch.setattr(api_modulu.webview, "create_window", olustur)
    return cagri


def test_giris_token_gelince_pencereyi_kapatir(api, monkeypatch):
    p = SahtePencere([None, "{}", ham()])
    cagri = pencere_ac(monkeypatch, p)
    istemci = api._elogo_giris()
    assert istemci is not None and p.kapatildi.is_set()
    assert "js_api" not in cagri          # portal Api'ye erişemesin
    assert api._elogo_pencere is None
    assert "gizli" not in repr(istemci)
    assert "gizli" not in repr(vars(api))


def test_kullanici_pencereyi_kapatirsa_none(api, monkeypatch):
    p = SahtePencere()
    pencere_ac(monkeypatch, p)
    threading.Timer(0.05, lambda: p.events.closed.isleyici()).start()
    assert api._elogo_giris() is None
    assert not p.kapatildi.is_set()       # kapanmış pencere yeniden kapatılmaz


def test_takilan_okuma_durdurla_kesilir(api, monkeypatch):
    p = SahtePencere()
    birak = threading.Event()
    p.evaluate_js = lambda kod: birak.wait(5)
    pencere_ac(monkeypatch, p)
    threading.Timer(0.05, api._stop_event.set).start()
    try:
        assert api._elogo_giris() is None
    finally:
        birak.set()
    assert p.kapatildi.is_set()


def test_hesap_bilgisi_bozuksa_pencere_acik_kalmaz(api, monkeypatch):
    p = SahtePencere([ham(profile={})])
    pencere_ac(monkeypatch, p)
    with pytest.raises(ElogoHatasi):
        api._elogo_giris()
    assert p.kapatildi.is_set()


def test_ana_pencere_kapanirken_giris_penceresi_de_kapanir(api):
    p = SahtePencere()
    api._elogo_pencere = p
    api._pencere = type("P", (), {"width": 800, "height": 600})()
    api._pencere_kapaniyor()
    assert p.kapatildi.is_set() and api._stop_event.is_set()


def test_elogo_indir_guvenlik_kontrolleri(api, tmp_path):
    assert "hata" in api.elogo_indir(None, "A")
    assert "hata" in api.elogo_indir(str(tmp_path), 5)
    assert "hata" in api.elogo_indir(str(tmp_path / "yok"), "A")
    assert "hata" in api.elogo_indir(str(tmp_path), "  \n ")
    api._calisiyor = True
    assert api.elogo_indir(str(tmp_path), "A") == {"hata": "Zaten bir işlem sürüyor."}
    api._calisiyor = False
    api._deneniyor = True
    assert "hata" in api.elogo_indir(str(tmp_path), "A")


def test_elogo_indir_uctan_uca_kilidi_birakir(api, tmp_path, monkeypatch):
    bitis = threading.Event()
    gelen = []

    def js(_fonksiyon, liste):
        gelen.extend(liste)
        if any(o["t"] == "elogo_ozet" for o in liste):
            bitis.set()
    monkeypatch.setattr(api, "_js", js)
    monkeypatch.setattr(api, "_elogo_giris", lambda: Sahte({"A1": [oge("1")]}))
    assert api.elogo_indir(str(tmp_path), "A1") == {"ok": True}
    assert bitis.wait(5)
    for _ in range(50):
        if not api._calisiyor:
            break
        threading.Event().wait(0.02)
    assert not api._calisiyor             # pompa bitti, yeni iş başlatılabilir
    assert (tmp_path / "A1.xml").exists()
    assert not (tmp_path / "gecmis.json").exists()   # eLogo indirmesi geçmişe girmez
    assert gelen[-1]["d"]["indirilen"] == ["A1"]


# ── Oturumun yeniden kullanımı ───────────────────────────────────────

def test_gecerli_oturum_ikinci_indirmede_pencere_acmaz(api, monkeypatch):
    p = SahtePencere([ham(expires_at=time.time() + 3600)])
    pencere_ac(monkeypatch, p)
    ilk = api._elogo_giris()
    monkeypatch.setattr(api_modulu().webview, "create_window",
                        lambda *a, **k: pytest.fail("pencere açılmamalıydı"))
    assert api._elogo_giris() is ilk


@pytest.mark.parametrize("kalan", [-5, 30, 100])
def test_suresi_bitmek_uzere_olan_oturum_yeniden_kullanilmaz(api, monkeypatch, kalan):
    """`elogo.py` son 60 sn'de oturum hatası verir; aynı istemci geri dönerse
    yenileme döngüsü aynı hatayı alıp işi durdururdu."""
    p = SahtePencere([ham(expires_at=time.time() + kalan), ham(expires_at=time.time() + 3600)])
    pencere_ac(monkeypatch, p)
    ilk = api._elogo_giris()
    assert api._elogo_giris() is not ilk
    assert p.cevaplar == []


def test_is_hatayla_biterse_oturum_unutulur(api, tmp_path):
    api._elogo_oturum = (Sahte(bul_hatasi=ElogoHatasi("iptal")), time.time() + 3600)
    api._elogo_calistir(["A"], [], str(tmp_path))
    assert api._elogo_oturum is None


def test_is_basariyla_biterse_oturum_kalir(api, tmp_path):
    oturum = (Sahte(), time.time() + 3600)
    api._elogo_oturum = oturum
    api._elogo_calistir(["A"], [], str(tmp_path))
    assert api._elogo_oturum is oturum


def test_oturum_nesnesi_tokeni_gostermez(api, monkeypatch):
    pencere_ac(monkeypatch, SahtePencere([ham(expires_at=time.time() + 3600)]))
    api._elogo_giris()
    assert "gizli" not in repr(api._elogo_oturum)
    assert "gizli" not in repr(vars(api))


# ── Geliştirme profili ───────────────────────────────────────────────

def test_exede_oturum_diske_yazilmaz(monkeypatch):
    import main
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    assert main.webview_ayarlari() == {}


def test_gelistirme_profili_kalici_ve_repo_disinda(monkeypatch, tmp_path):
    import main
    monkeypatch.delattr(main.sys, "frozen", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    ayar = main.webview_ayarlari()
    assert ayar["private_mode"] is False
    profil = pathlib.Path(ayar["storage_path"])
    assert profil.is_dir() and tmp_path in profil.parents
    assert pathlib.Path.cwd() not in profil.parents
    assert ayar["http_port"] > 0              # sabit porta düşmesin
