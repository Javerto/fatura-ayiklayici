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
