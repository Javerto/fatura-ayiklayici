"""İnceleme taslağı — onay bekleyen satırlar diske yazılır.

Taslak yoksa pencere kapanınca ya da uygulama çökünce yüzlerce faturanın
çıkarımı (harcanan Gemini kotası) ve kullanıcının düzeltmeleri kaybolur.
"""
import datetime

import pytest

import sema
from api import Api
from excel_utils import excel_olustur, mevcut_verileri_oku
from hatalar import ExcelHatasi


def _satir(no):
    return {"fatura_no": no, "sirket_adi": "ACME A.Ş.", "vkn": "1234567890",
            "vergi_dairesi": "Büyük Mükellefler",
            "vergiler_dahil_tutar": 1180.0, "kdv_haric_tutar": 1000.0,
            "para_birimi": "TRY", "fatura_tarihi": datetime.datetime(2024, 1, 15),
            "dosya_yolu": rf"C:\x\{no}.pdf", "_teknik_bilgi": "Dijital"}


def _api(kok):
    a = Api(kok=kok)
    a._pencere = type("P", (), {"evaluate_js": lambda self, k: None})()
    return a


def _review_gelsin(api, tmp_path, yeni, mevcut=()):
    """Worker'ın review olayını pompadan geçirir (gerçek yol)."""
    api._log_q.put(("review", {
        "mevcut": list(mevcut), "yeni": list(yeni), "atlanmis": [("bozuk.pdf", "okunamadı")],
        "uyarilar": [], "cikti": str(tmp_path / "faturalar.xlsx"), "kesildi": True,
        "sema_farki": None, "sema": sema.VARSAYILAN}))
    api._pompa_dongusu()


def _form(api, i, **degisen):
    olay = api._review_olayi(api._review)
    return {**olay["satirlar"][i]["form"], **degisen}


@pytest.fixture
def kok(tmp_path):
    k = tmp_path / "ayar"
    k.mkdir()
    return k


def test_review_gelince_taslak_yazilir_ve_tur_atar(kok, tmp_path):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    assert (kok / "inceleme_taslagi.pkl").exists()

    yeni = _api(kok)                      # uygulama yeniden açıldı
    ozet = yeni.baslangic_durumu()["taslak"]
    assert ozet["sayi"] == 1 and ozet["cikti"] == "faturalar.xlsx"
    olay = yeni.taslak_devam()
    assert olay["t"] == "review" and olay["kesildi"] is True and olay["atlanan"] == 1
    assert yeni._review["yeni"][0]["fatura_tarihi"] == datetime.datetime(2024, 1, 15)
    assert yeni._review["sema"] == sema.VARSAYILAN


def test_duzenleme_taslaga_yazilir_ve_onayda_excele_gider(kok, tmp_path):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    api.satir_dogrula(0, _form(api, 0, sirket_adi="DÜZELTİLMİŞ A.Ş."))

    yeni = _api(kok)
    yeni.baslangic_durumu()
    olay = yeni.taslak_devam()
    assert olay["satirlar"][0]["form"]["sirket_adi"] == "DÜZELTİLMİŞ A.Ş."
    assert olay["duzenlemeler"]["0"]["sirket_adi"] == "DÜZELTİLMİŞ A.Ş."
    # Arayüz taslaktaki düzenlemeleri onayda geri yollar.
    sonuc = yeni.review_onayla(olay["duzenlemeler"], [], [])
    assert sonuc["ok"]
    satirlar, _ = mevcut_verileri_oku(str(tmp_path / "faturalar.xlsx"))
    assert satirlar[0]["sirket_adi"] == "DÜZELTİLMİŞ A.Ş."
    assert not (kok / "inceleme_taslagi.pkl").exists()


@pytest.mark.parametrize("haric", [[], [0]])      # yazılan ve dokunulmadı dalları
def test_onayda_taslak_silinir(kok, tmp_path, haric):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    assert api.review_onayla({}, haric, [])["ok"]
    assert not (kok / "inceleme_taslagi.pkl").exists()


def test_iptalde_taslak_silinir(kok, tmp_path):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    api.review_iptal()
    assert not (kok / "inceleme_taslagi.pkl").exists()


def test_excel_hatasinda_taslak_kalir(kok, tmp_path, monkeypatch):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    monkeypatch.setattr("api.excel_olustur",
                        lambda *a: (_ for _ in ()).throw(ExcelHatasi("kilitli")))
    assert api.review_onayla({}, [], []) == {"hata": "kilitli"}
    assert (kok / "inceleme_taslagi.pkl").exists()


@pytest.mark.parametrize("icerik", [b"bozuk veri", b"\x80\x04K\x01."])  # çöp; geçerli pickle ama int
def test_bozuk_taslak_cokertmez_ve_yedeklenir(kok, icerik):
    (kok / "inceleme_taslagi.pkl").write_bytes(icerik)
    api = _api(kok)
    taslak = api.baslangic_durumu()["taslak"]
    assert "hata" in taslak
    assert not (kok / "inceleme_taslagi.pkl").exists()
    yedekler = list(kok.glob("inceleme_taslagi*.bozuk"))
    assert len(yedekler) == 1 and yedekler[0].read_bytes() == icerik
    assert api.taslak_devam() == {"hata": "Devam edilecek bir inceleme yok."}


def test_taslak_yokken_ozet_bos(kok):
    assert _api(kok).baslangic_durumu()["taslak"] is None


def test_taslak_sil(kok, tmp_path):
    _review_gelsin(_api(kok), tmp_path, [_satir("GIB2024000000101")])
    api = _api(kok)
    api.baslangic_durumu()
    assert api.taslak_sil() == {"ok": True}
    assert not (kok / "inceleme_taslagi.pkl").exists()


def test_inceleme_acikken_taslak_silinemez(kok, tmp_path):
    """JS bir güven sınırı: açık incelemenin taslağı arayüzden silinmemeli."""
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    assert "hata" in api.taslak_sil()
    assert (kok / "inceleme_taslagi.pkl").exists()
    assert "hata" in api.taslak_devam()


def test_excel_degistiyse_mevcut_yeniden_okunur(kok, tmp_path):
    """Taslaktan sonra başka bir koşu onaylanmışsa eski `mevcut` ile yazmak
    o koşunun faturalarını Excel'den silerdi."""
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    cikti = str(tmp_path / "faturalar.xlsx")
    excel_olustur([_satir("GIB2024000000999")], cikti, sema.VARSAYILAN)

    yeni = _api(kok)
    yeni.baslangic_durumu()
    olay = yeni.taslak_devam()
    assert olay["excel_degisti"] is True and olay["mevcut_sayi"] == 1
    yeni.review_onayla({}, [], [])
    satirlar, _ = mevcut_verileri_oku(cikti)
    assert {s["fatura_no"] for s in satirlar} == {"GIB2024000000999", "GIB2024000000101"}


def test_excel_okunamazsa_devam_edilmez_taslak_kalir(kok, tmp_path, monkeypatch):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    (tmp_path / "faturalar.xlsx").write_bytes(b"excel degil")

    yeni = _api(kok)
    yeni.baslangic_durumu()
    assert yeni.taslak_devam()["tekrar"] is True
    assert yeni._review is None
    assert (kok / "inceleme_taslagi.pkl").exists()


@pytest.mark.parametrize("form", [None, "x", {"sirket_adi": 5}])
def test_satir_dogrula_gecersiz_formu_reddeder(kok, tmp_path, form):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    api.satir_dogrula(0, form)            # JS'ten gelen çöp çökertmemeli
    assert api._duzenlemeler.get(0, {}).get("sirket_adi") is None


def test_haric_tutma_taslaga_yazilir(kok, tmp_path):
    """Taslaktan dönünce hariç tutulanlar sıfırlansa, kullanıcının ayıkladığı
    mükerrer faturalar fark edilmeden Excel'e yazılırdı."""
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101"), _satir("GIB2024000000102")])
    assert api.review_haric(1, True) is True
    assert api.review_haric(0, True) is True
    assert api.review_haric(0, False) is True

    yeni = _api(kok)
    yeni.baslangic_durumu()
    assert yeni.taslak_devam()["haric"] == [1]


@pytest.mark.parametrize("i, durum", [(5, True), (-1, True), ("x", True), (0, "evet")])
def test_review_haric_gecersiz_girdiyi_reddeder(kok, tmp_path, i, durum):
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    assert api.review_haric(i, durum) is False
    assert api._haric == set()


def test_bekleyen_taslak_varken_yeni_kosu_baslamaz(kok, tmp_path, monkeypatch):
    """Yeni koşunun review'ı taslağın üstüne yazılır; karar verilmemiş eski
    inceleme (harcanan kota) sessizce giderdi."""
    _review_gelsin(_api(kok), tmp_path, [_satir("GIB2024000000101")])
    api = _api(kok)
    api.baslangic_durumu()
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr("api.worker", lambda *a, **k: None)
    sonuc = api.basla({"klasor": str(tmp_path), "cikti": "x"})
    assert "yarım kalan" in sonuc.get("hata", "") and not api._calisiyor


def test_bitmis_incelemenin_taslagi_yeniden_yazilmaz(kok, tmp_path):
    """Onayla ile alandan çıkış yarışırsa geç kalan yazma silinen taslağı
    diriltmemeli; yoksa onaylanmış inceleme açılışta yeniden sorulur."""
    api = _api(kok)
    _review_gelsin(api, tmp_path, [_satir("GIB2024000000101")])
    api._review_bitir()
    api._taslak_yaz()
    assert not (kok / "inceleme_taslagi.pkl").exists()


def test_taslak_devam_beklenmeyen_hatada_yedekler(kok, tmp_path, monkeypatch):
    """Okunup açılamayan taslak her açılışta aynı soruyu sorup sessizce
    düşmemeli: hata dönülür, dosya yedeklenir."""
    _review_gelsin(_api(kok), tmp_path, [_satir("GIB2024000000101")])
    api = _api(kok)
    api.baslangic_durumu()
    monkeypatch.setattr(api, "_review_olayi", lambda p: 1 / 0)
    assert "hata" in api.taslak_devam()
    assert api._review is None and api._taslak_bekleyen is None   # basla kilitli kalmasın
    assert not (kok / "inceleme_taslagi.pkl").exists()
    assert len(list(kok.glob("inceleme_taslagi*.bozuk"))) == 1
