"""extraction.py saf yardımcı fonksiyonları: to_float, tarih_parse, veri_dogrula."""

from datetime import datetime

import pytest

from extraction import to_float, tarih_parse, veri_dogrula


# ─── to_float ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("girdi, beklenen", [
    ("1.234,56", 1234.56),      # TR format: binlik nokta + ondalık virgül
    ("1000,50", 1000.50),       # sadece ondalık virgül
    ("1000.00", 1000.0),        # standart ondalık nokta
    ("14.5", 14.5),             # tek ondalık nokta — standart float kabul edilir
    ("1.234.567", 1234567.0),   # çok parçalı TR binlik
    ("1.234", 1234.0),          # tek gruplu TR binlik — eskiden 1,234 oluyordu
    ("1,234.56", 1234.56),      # US format: son ayırıcı ondalıktır
    ("1,234,567", 1234567.0),   # US binlik virgül (birden fazla virgül)
    ("12,50 TL", 12.5),         # birim ekli — eskiden None oluyordu
    ("₺1.234,56", 1234.56),     # sembol önde
    ("-1.234,56", -1234.56),    # negatif
    ("0.50", 0.5),              # ondalık nokta, binlik sanılmamalı
    (1234, 1234.0),             # int passthrough
    (12.5, 12.5),               # float passthrough
])
def test_to_float_gecerli(girdi, beklenen):
    assert to_float(girdi) == beklenen


@pytest.mark.parametrize("girdi", [None, "", "abc", "  "])
def test_to_float_gecersiz_none_doner(girdi):
    assert to_float(girdi) is None


# ─── tarih_parse ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("girdi", [
    "2024-01-15",
    "15.01.2024",
    "15-01-2024",
    "15/01/2024",
])
def test_tarih_parse_gecerli_formatlar(girdi):
    assert tarih_parse(girdi) == datetime(2024, 1, 15)


def test_tarih_parse_okunamayan_orijinali_doner():
    assert tarih_parse("bozuk tarih") == "bozuk tarih"


@pytest.mark.parametrize("girdi", [None, ""])
def test_tarih_parse_bos_oldugu_gibi_doner(girdi):
    assert tarih_parse(girdi) == girdi


# ─── veri_dogrula ────────────────────────────────────────────────────────────

def _temiz_veri():
    return {
        "fatura_no":            "GIB2024123456789",
        "fatura_tarihi":        datetime(2024, 1, 15),
        "sirket_adi":           "ACME A.Ş.",
        "vkn":                  "1234567890",
        "vergiler_dahil_tutar": 1180.0,
        "para_birimi":          "TL",
        "sira_no":              None,
    }


def test_veri_dogrula_temiz_veri_uyari_yok():
    assert veri_dogrula(_temiz_veri()) == []


def test_veri_dogrula_bos_fatura_no():
    v = _temiz_veri()
    v["fatura_no"] = ""
    assert ("fatura_no", "Fatura no boş") in veri_dogrula(v)


def test_veri_dogrula_yalnizca_rakam_fatura_no():
    v = _temiz_veri()
    v["fatura_no"] = "1234567890123456"
    assert any(a == "fatura_no" and "yalnızca rakam" in m for a, m in veri_dogrula(v))


def test_veri_dogrula_gecersiz_vkn():
    v = _temiz_veri()
    v["vkn"] = "123"
    assert any(a == "vkn" and "VKN" in m for a, m in veri_dogrula(v))


def test_veri_dogrula_eksik_tutar():
    v = _temiz_veri()
    v["vergiler_dahil_tutar"] = None
    assert ("vergiler_dahil_tutar", "Vergiler dahil tutar boş") in veri_dogrula(v)


def test_veri_dogrula_bos_tarih():
    """Boş tarih uyarısızdı: satır 'temiz' görünüp Excel'e tarihsiz yazılıyordu."""
    v = _temiz_veri()
    v["fatura_tarihi"] = ""
    assert ("fatura_tarihi", "Fatura tarihi boş") in veri_dogrula(v)
    v["fatura_tarihi"] = None
    assert ("fatura_tarihi", "Fatura tarihi boş") in veri_dogrula(v)


def test_veri_dogrula_okunmamis_tarih_string():
    v = _temiz_veri()
    v["fatura_tarihi"] = "15 Mart 2024"
    assert any(a == "fatura_tarihi" and "Tarih okunamadı" in m for a, m in veri_dogrula(v))


def test_veri_dogrula_bilinmeyen_para_birimi():
    v = _temiz_veri()
    v["para_birimi"] = "GBP"
    assert any(a == "para_birimi" and "Bilinmeyen para birimi" in m for a, m in veri_dogrula(v))


def test_veri_dogrula_sira_no_tesvik_karismasi():
    v = _temiz_veri()
    v["sira_no"] = 1500
    assert any(a == "sira_no" and "teşvik" in m for a, m in veri_dogrula(v))
