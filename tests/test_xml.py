"""xml_den_veri_cek — UBL e-fatura ayrıştırma (örnek fixture ile)."""

import pathlib
from datetime import datetime

import pytest

from extraction import xml_den_veri_cek
from hatalar import XMLHatasi

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ornek_fatura.xml"


@pytest.fixture
def veri():
    return xml_den_veri_cek(str(FIXTURE), None)


def test_fatura_no(veri):
    assert veri["fatura_no"] == "GIB2024000000123"


def test_tarih_datetime_olur(veri):
    assert veri["fatura_tarihi"] == datetime(2024, 3, 15)


def test_satici_bilgileri(veri):
    assert veri["sirket_adi"] == "ACME Bilisim A.S."
    assert veri["vkn"] == "1234567890"
    assert veri["vergi_dairesi"] == "Buyuk Mukellefler"


def test_tutarlar(veri):
    assert veri["kdv_haric_tutar"] == 1000.0
    assert veri["vergiler_dahil_tutar"] == 1180.0
    assert veri["para_birimi"] == "TRY"


def test_toplam_miktar_satirlardan_toplanir(veri):
    assert veri["toplam_miktar"] == 5.0


def test_tanim_ilk_kalemden(veri):
    assert veri["tanim"] == "Yazilim lisansi"


def test_sira_no_nottan_cikar(veri):
    assert veri["sira_no"] == 5.0


def test_dosya_yolu_xml_yolu_olur(veri):
    # pdf_yolu None ise dosya_yolu XML'in mutlak yoludur
    assert veri["dosya_yolu"] == str(FIXTURE.resolve())


def test_bozuk_xml_hata_firlatir(tmp_path):
    bozuk = tmp_path / "bozuk.xml"
    bozuk.write_text("<Invoice><eksik", encoding="utf-8")
    with pytest.raises(XMLHatasi):
        xml_den_veri_cek(str(bozuk), None)
