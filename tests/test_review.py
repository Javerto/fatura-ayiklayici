"""review.py saf mantık testleri."""
from datetime import datetime

import pytest

from review import (DUZENLENEBILIR_ALANLAR, satir_form_degerleri)


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


from review import form_satira_uygula


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
