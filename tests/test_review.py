"""review.py saf mantık testleri."""
from datetime import datetime

from extraction import veri_dogrula
from review import (DUZENLENEBILIR_ALANLAR, satir_form_degerleri,
                    form_satira_uygula, nihai_satirlar)


def test_form_degerleri_tarih_ve_sayi_metne_cevrilir():
    row = {"fatura_no": "GIB2024123456789", "fatura_tarihi": datetime(2024, 3, 15),
           "toplam_miktar": 5.0, "vergiler_dahil_tutar": 1180.0,
           "sira_no": None, "para_birimi": "TL"}
    f = satir_form_degerleri(row)
    assert f["fatura_tarihi"] == "15.03.2024"
    assert f["toplam_miktar"] == "5"          # tam sayı float → ondalıksız
    assert f["vergiler_dahil_tutar"] == "1180"
    assert f["sira_no"] == ""                 # None → boş
    assert f["para_birimi"] == "TL"


def test_form_degerleri_tum_alanlar_string_ve_eksiksiz():
    f = satir_form_degerleri({})
    assert set(f.keys()) == {a for a, _, _ in DUZENLENEBILIR_ALANLAR}
    assert all(isinstance(v, str) for v in f.values())


def _bos_form():
    return {a: "" for a, _, _ in DUZENLENEBILIR_ALANLAR}


def test_uygula_sayi_ve_tarih_cevirir():
    form = {**_bos_form(),
            "fatura_no": "GIB2024123456789", "fatura_tarihi": "15.03.2024",
            "vergiler_dahil_tutar": "1.234,56", "toplam_miktar": "5",
            "sirket_adi": "ACME", "vkn": "1234567890"}
    y = form_satira_uygula({"dosya_yolu": "x.pdf"}, form)
    assert y["vergiler_dahil_tutar"] == 1234.56
    assert y["fatura_tarihi"] == datetime(2024, 3, 15)
    assert y["toplam_miktar"] == 5.0
    assert y["sira_no"] is None              # boş sayı → None
    assert y["dosya_yolu"] == "x.pdf"        # düzenlenmeyen alan korunur


def test_uygula_gecersiz_tarih_metin_kalir():
    y = form_satira_uygula({}, {**_bos_form(), "fatura_tarihi": "abc"})
    assert y["fatura_tarihi"] == "abc"


def test_uygula_orijinal_satiri_bozmaz():
    row = {"fatura_no": "ESKI"}
    form_satira_uygula(row, {**_bos_form(), "fatura_no": "YENI"})
    assert row["fatura_no"] == "ESKI"        # kopya döner, mutasyon yok


def test_nihai_satirlar_haric_tutulanlari_cikarir():
    mevcut = [{"fatura_no": "M"}]
    yeni = [{"fatura_no": "A"}, {"fatura_no": "B"}, {"fatura_no": "C"}]
    sonuc = nihai_satirlar(mevcut, yeni, {1})
    assert [s["fatura_no"] for s in sonuc] == ["M", "A", "C"]


def test_nihai_satirlar_bos_haric():
    assert nihai_satirlar([], [{"x": 1}], set()) == [{"x": 1}]


def test_revalidation_kapanisi_vkn_duzeltince_uyari_kalkar():
    row = {"fatura_no": "GIB2024123456789", "vergiler_dahil_tutar": 100.0,
           "para_birimi": "TL", "sirket_adi": "ACME",
           "fatura_tarihi": datetime(2024, 1, 1), "vkn": "123"}
    assert any("VKN" in u for u in veri_dogrula(row))
    duzeltilmis = form_satira_uygula(
        row, {**satir_form_degerleri(row), "vkn": "1234567890"})
    assert not any("VKN" in u for u in veri_dogrula(duzeltilmis))
