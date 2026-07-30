"""review_onayla — Excel'in yazıldığı tek yol.

Bu dosyadaki her test, kırıldığında kullanıcının ne kaybedeceğini anlatır.
"""
import datetime
import json

import pytest

from api import Api
from excel_utils import ExcelHatasi, mevcut_verileri_oku


def _satir(no, sirket="ACME A.Ş.", vkn="1234567890"):
    return {"fatura_no": no, "sirket_adi": sirket, "vkn": vkn,
            "vergi_dairesi": "Büyük Mükellefler",
            "vergiler_dahil_tutar": 1180.0, "kdv_haric_tutar": 1000.0,
            "para_birimi": "TRY", "fatura_tarihi": datetime.datetime(2024, 1, 15),
            "dosya_yolu": rf"C:\x\{no}.pdf", "_teknik_bilgi": "Dijital"}


@pytest.fixture
def api(tmp_path):
    """Ayar dosyaları tmp_path'te — gerçek .env/gecmis.json kirlenmesin."""
    a = Api(kok=tmp_path)
    a._pencere = type("P", (), {"evaluate_js": lambda self, k: None})()
    return a


def _review_kur(api, tmp_path, yeni, mevcut=()):
    cikti = str(tmp_path / "faturalar.xlsx")
    api._review = {"mevcut": list(mevcut), "yeni": list(yeni),
                   "atlanmis": [], "cikti": cikti, "kesildi": False}
    return cikti


def test_duzenleme_excele_yansir(api, tmp_path):
    cikti = _review_kur(api, tmp_path, [_satir("GIB2024000000101")])
    form = {"fatura_no": "GIB2024000000101", "sirket_adi": "DÜZELTİLMİŞ A.Ş.",
            "vkn": "1234567890", "vergi_dairesi": "Kadıköy",
            "fatura_tarihi": "15.01.2024", "tanim": "", "toplam_miktar": "",
            "kdv_haric_tutar": "1000", "vergiler_dahil_tutar": "1180",
            "para_birimi": "TRY", "sira_no": ""}
    sonuc = api.review_onayla({"0": form}, [], [])

    assert sonuc["ok"] and sonuc["yazilan"] == 1
    satirlar, _ = mevcut_verileri_oku(cikti)
    assert satirlar[0]["sirket_adi"] == "DÜZELTİLMİŞ A.Ş."


def test_haric_tutulan_satir_yazilmaz(api, tmp_path):
    cikti = _review_kur(api, tmp_path,
                        [_satir("GIB2024000000101"), _satir("GIB2024000000102")])
    api.review_onayla({}, [1], [])
    satirlar, _ = mevcut_verileri_oku(cikti)
    assert [s["fatura_no"] for s in satirlar] == ["GIB2024000000101"]


def test_tum_yeniler_haric_ise_excele_dokunulmaz(api, tmp_path):
    """Dosya hiç yaratılmamalı; mevcut bir dosya varsa da bozulmamalı."""
    cikti = _review_kur(api, tmp_path, [_satir("GIB2024000000101")])
    sonuc = api.review_onayla({}, [0], [])
    assert sonuc["dokunulmadi"] is True
    assert not (tmp_path / "faturalar.xlsx").exists()


def test_excel_hatasinda_review_korunur(api, tmp_path, monkeypatch):
    """Dosya kilitliyken düzenlemeler kaybolmamalı — pencere açık kalır."""
    _review_kur(api, tmp_path, [_satir("GIB2024000000101")])
    monkeypatch.setattr("api.excel_olustur",
                        lambda *a: (_ for _ in ()).throw(ExcelHatasi("kilitli")))
    sonuc = api.review_onayla({}, [], [])
    assert sonuc == {"hata": "kilitli"}
    assert api._review is not None, "düzenlemeler çöpe atıldı"


def test_haric_tutulan_satirdan_kural_ogrenilmez(api, tmp_path):
    """Kullanıcının çöpe attığı satırdan kalıcı VKN kuralı yazılırsa o firmanın
    sonraki tüm faturaları sessizce bozulur."""
    _review_kur(api, tmp_path,
                [_satir("GIB2024000000101", "DOĞRU A.Ş.", "1111111111"),
                 _satir("GIB2024000000102", "YANLIŞ A.Ş.", "2222222222")])
    api.review_onayla({}, [1], [0, 1])          # 1 hem hariç hem "hatırla"

    kurallar = json.loads((tmp_path / "duzeltmeler.json").read_text("utf-8"))
    assert "1111111111" in kurallar
    assert "2222222222" not in kurallar


def test_gecersiz_duzenleme_indeksi_yok_sayilir(api, tmp_path):
    """JS bir güven sınırı; sınır dışı indeks IndexError ile patlamamalı."""
    cikti = _review_kur(api, tmp_path, [_satir("GIB2024000000101")])
    sonuc = api.review_onayla({"5": {}, "-1": {}, "abc": {}}, [], [])
    assert sonuc["ok"]
    satirlar, _ = mevcut_verileri_oku(cikti)
    assert [s["fatura_no"] for s in satirlar] == ["GIB2024000000101"]


def test_mevcut_satirlar_korunur(api, tmp_path):
    """Yeni faturalar eskilerin üzerine değil, yanına yazılmalı."""
    cikti = _review_kur(api, tmp_path, [_satir("GIB2024000000102")],
                        mevcut=[_satir("GIB2024000000101")])
    api.review_onayla({}, [], [])
    satirlar, _ = mevcut_verileri_oku(cikti)
    assert sorted(s["fatura_no"] for s in satirlar) == \
        ["GIB2024000000101", "GIB2024000000102"]
