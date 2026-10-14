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


# GİB UBL-TR'de satıcı VKN'si PartyIdentification/cbc:ID[@schemeID="VKN"]
# içinde durur; PartyTaxScheme/CompanyID çoğu faturada hiç yoktur. eLogo'dan
# inen gerçek faturaların hepsinde VKN böyle boş geliyordu. Şahıs satıcıda
# şema "TCKN" olur; ID'lerin sırası faturaya göre değişir.
def _satici_xml(tmp_path, kimlikler):
    ids = "".join(
        f'<cac:PartyIdentification><cbc:ID schemeID="{s}">{v}</cbc:ID></cac:PartyIdentification>'
        for s, v in kimlikler)
    yol = tmp_path / "ubltr.xml"
    yol.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:ID>ABC2026000000001</cbc:ID>
  <cac:AccountingSupplierParty><cac:Party>
    {ids}
    <cac:PartyName><cbc:Name>Ornek A.S.</cbc:Name></cac:PartyName>
    <cac:PartyTaxScheme><cac:TaxScheme><cbc:Name>PENDIK</cbc:Name></cac:TaxScheme></cac:PartyTaxScheme>
  </cac:Party></cac:AccountingSupplierParty>
</Invoice>""", encoding="utf-8")
    return str(yol)


def test_vkn_party_identification_dan_okunur(tmp_path):
    yol = _satici_xml(tmp_path, [("TICARETSICILNO", "12345678"),
                                 ("MERSISNO", "0123456789000015"),
                                 ("VKN", "9876543210")])
    assert xml_den_veri_cek(yol, None)["vkn"] == "9876543210"


def test_sahis_saticida_tckn_okunur(tmp_path):
    yol = _satici_xml(tmp_path, [("TCKN", "12345678901")])
    assert xml_den_veri_cek(yol, None)["vkn"] == "12345678901"
