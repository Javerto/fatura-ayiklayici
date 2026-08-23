"""Mükerrer fatura uyarısı.

Arşivin tekilliği `mevcut_verileri_oku`'da dosya adından geliyor; aynı fatura
farklı adla klasöre düşerse (portaldan ikinci indirme) o kontrol tutmuyor ve
fatura arşive ikinci kez yazılıyor. Bu uyarı onu gözden geçirme ekranında
gösterir — veriyi reddetmez, hariç tutma kullanıcının kararıdır.
"""
import datetime

import pytest

from api import Api
from extraction import veri_dogrula


def _satir(no, ad=None):
    return {"fatura_no": no, "sirket_adi": "ACME A.Ş.", "vkn": "1234567890",
            "vergiler_dahil_tutar": 1180.0, "kdv_haric_tutar": 1000.0,
            "para_birimi": "TRY", "fatura_tarihi": datetime.datetime(2024, 1, 15),
            "dosya_yolu": rf"C:\x\{ad or no}.pdf", "_teknik_bilgi": "Dijital"}


def _no_uyarilari(satirlar_uyarilar):
    return [m for a, m in satirlar_uyarilar if a == "fatura_no"]


# ── veri_dogrula: saf mantık ─────────────────────────────────────────

def test_baska_nolar_verilmezse_mukerrer_uyarisi_yok():
    """Geriye dönük uyum: tek argümanla çağıran her yer eskisi gibi çalışır."""
    assert _no_uyarilari(veri_dogrula(_satir("GIB2024000000101"))) == []


def test_arsivde_ayni_no_varsa_uyarir():
    uyarilar = _no_uyarilari(
        veri_dogrula(_satir("GIB2024000000101"), {"GIB2024000000101"}))
    assert any("mükerrer" in m for m in uyarilar)


def test_karsilastirma_harf_buyuklugune_duyarsiz():
    """Excel'den okunan eski satır ile model çıktısı yalnızca büyük/küçük
    harfte ayrışabilir; ayrışma mükerreri gizlememeli."""
    uyarilar = _no_uyarilari(
        veri_dogrula(_satir("gib2024000000101"), {"GIB2024000000101"}))
    assert any("mükerrer" in m for m in uyarilar)


def test_farkli_no_uyarmaz():
    uyarilar = _no_uyarilari(
        veri_dogrula(_satir("GIB2024000000102"), {"GIB2024000000101"}))
    assert not any("mükerrer" in m for m in uyarilar)


# ── Api: gözden geçirme ekranına giden uyarılar ──────────────────────

@pytest.fixture
def api(tmp_path):
    a = Api(kok=tmp_path)
    a._pencere = type("P", (), {"evaluate_js": lambda self, k: None})()
    return a


def _payload(yeni, mevcut=()):
    return {"mevcut": list(mevcut), "yeni": list(yeni), "atlanmis": [],
            "cikti": "x.xlsx", "kesildi": False}


def test_ayni_kosuda_iki_kopya_ikisi_de_isaretlenir(api):
    """Kullanıcı hangisini atacağını seçebilmeli; tek kopyayı işaretlemek
    hangisinin 'asıl' olduğu kararını sessizce bizim vermemiz olurdu."""
    api._review = _payload([_satir("GIB2024000000101", ad="fatura"),
                            _satir("GIB2024000000101", ad="fatura(1)")])
    olay = api._review_olayi(api._review)
    for satir in olay["satirlar"]:
        assert any("mükerrer" in m for _, m in satir["uyarilar"]), satir["dosya"]


def test_arsivdeki_kayitla_cakisma_isaretlenir(api):
    api._review = _payload([_satir("GIB2024000000101", ad="yeniden-indirildi")],
                           mevcut=[_satir("GIB2024000000101")])
    olay = api._review_olayi(api._review)
    assert any("mükerrer" in m for _, m in olay["satirlar"][0]["uyarilar"])


def test_tekil_faturalar_isaretlenmez(api):
    api._review = _payload([_satir("GIB2024000000101"),
                            _satir("GIB2024000000102")],
                           mevcut=[_satir("GIB2024000000103")])
    olay = api._review_olayi(api._review)
    for satir in olay["satirlar"]:
        assert not any("mükerrer" in m for _, m in satir["uyarilar"])


def test_bos_fatura_no_mukerrer_sayilmaz(api):
    """İki satırda da no boşsa bu mükerrerlik değil, iki ayrı eksik veridir."""
    api._review = _payload([_satir("", ad="a"), _satir("", ad="b")])
    olay = api._review_olayi(api._review)
    for satir in olay["satirlar"]:
        assert not any("mükerrer" in m for _, m in satir["uyarilar"])


def test_duzeltilen_no_mukerrere_dusunce_uyarir(api):
    """Kullanıcı ikinci satırın no'sunu birincininkine çevirirse anında görsün."""
    api._review = _payload([_satir("GIB2024000000101"),
                            _satir("GIB2024000000102")])
    form = {"fatura_no": "GIB2024000000101", "sirket_adi": "ACME A.Ş.",
            "vkn": "1234567890", "vergi_dairesi": "", "fatura_tarihi": "15.01.2024",
            "tanim": "", "toplam_miktar": "", "kdv_haric_tutar": "1000",
            "vergiler_dahil_tutar": "1180", "para_birimi": "TRY", "sira_no": ""}
    uyarilar = api.satir_dogrula(1, form)
    assert any("mükerrer" in m for _, m in uyarilar)


def test_satirin_kendi_nosu_kendini_mukerrer_yapmaz(api):
    """Düzenlenen satır karşılaştırma kümesinden çıkarılmazsa her satır
    kendisiyle çakışır ve tüm ekran uyarı dolar."""
    api._review = _payload([_satir("GIB2024000000101")])
    form = {"fatura_no": "GIB2024000000101", "sirket_adi": "ACME A.Ş.",
            "vkn": "1234567890", "vergi_dairesi": "", "fatura_tarihi": "15.01.2024",
            "tanim": "", "toplam_miktar": "", "kdv_haric_tutar": "1000",
            "vergiler_dahil_tutar": "1180", "para_birimi": "TRY", "sira_no": ""}
    uyarilar = api.satir_dogrula(0, form)
    assert not any("mükerrer" in m for _, m in uyarilar)
