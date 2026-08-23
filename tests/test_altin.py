"""Altın küme karşılaştırmasının kontrolü.

`altin.py`'nin kendisi ağa çıkar (pytest değil, elle çalıştırılan betik); ama
karşılaştırma mantığı sessizce bozulursa rapor yalan söyler — ölçülen tek yer o.
"""
from datetime import datetime

from altin import esit, karsilastir


def test_sayi_kurus_toleransi_ve_tr_format():
    assert esit("1.234,56", 1234.56, "sayi")
    assert esit(1234.56, 1234.565, "sayi")      # kuruş altı fark
    assert not esit(1234.56, 1234.60, "sayi")


def test_tarih_farkli_formatlar_esit():
    assert esit("15.03.2026", datetime(2026, 3, 15), "tarih")
    assert not esit("15.03.2026", datetime(2026, 3, 16), "tarih")


def test_metin_bosluk_ve_buyuk_harf_farkini_yutar():
    assert esit("ABC  Sanayi   A.Ş.", "abc sanayi a.ş.", "metin")
    assert not esit("ABC Sanayi", "ABD Sanayi", "metin")


def test_bos_ve_none_ayni_sayilir():
    assert esit(None, "", "metin")
    assert not esit("X", None, "metin")


def test_karsilastir_sadece_beklenendeki_alanlara_bakar():
    beklenen = {"fatura_no": "GIB2026000000001"}
    bulunan  = {"fatura_no": "GIB2026000000001", "vkn": "1234567890"}
    assert karsilastir(beklenen, bulunan) == []


def test_karsilastir_uyusmayani_dondurur():
    fark = karsilastir({"vkn": "1234567890"}, {"vkn": "9999999999"})
    assert fark == [("vkn", "1234567890", "9999999999")]


def test_bilinmeyen_alan_sessizce_gecmez():
    """Beklenen JSON'daki yazım hatası, alan doğruymuş gibi görünmemeli."""
    fark = karsilastir({"fatura_nu": "X"}, {"fatura_no": "X"})
    assert fark and fark[0][0] == "fatura_nu"
