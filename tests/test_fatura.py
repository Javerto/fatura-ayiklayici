"""Türetilmiş alanlar: dört modülün paylaştığı kural burada çivilenir."""
from fatura import kaynak, dosya_adi


def test_teknik_bilgi_uzantidan_once_gelir():
    assert kaynak({"_teknik_bilgi": "Dijital",
                   "dosya_yolu": r"C:\a\f.xml"}) == "Dijital"


def test_teknik_bilgi_yoksa_xml_uzantisindan():
    assert kaynak({"dosya_yolu": r"C:\a\F.XML"}) == "XML"


def test_bilinmeyen_varsayilani_cagirana_ait():
    # excel/worker/api boş bırakır, özet "Bilinmiyor" yazar.
    bos = {"dosya_yolu": r"C:\a\f.pdf"}
    assert kaynak(bos) == ""
    assert kaynak(bos, "Bilinmiyor") == "Bilinmiyor"


def test_bos_teknik_bilgi_uzantiya_duser():
    assert kaynak({"_teknik_bilgi": "  ", "dosya_yolu": "f.xml"}) == "XML"


def test_dosya_adi():
    assert dosya_adi({"dosya_yolu": r"C:\a\b\fatura.pdf"}) == "fatura.pdf"
    assert dosya_adi({}) == ""
    assert dosya_adi({"dosya_yolu": None}, "bilinmiyor") == "bilinmiyor"
