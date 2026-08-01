"""Alan tablosu ve türetilmiş alanlar: modüllerin paylaştığı şema burada çivilenir."""
from fatura import (ALANLAR, DUZENLENEBILIR_ALANLAR, OGRENILEN_ALANLAR, SUTUN,
                    kaynak, dosya_adi)


def test_excel_sutun_konumlari_degismez():
    """Eski Excel dosyaları bu konumlardan okunuyor; kaymaları arşivi bozar."""
    assert SUTUN == {
        "ft_formul": 1, "fatura_no": 2, "fatura_tarihi": 3, "sira_no": 4,
        "tanim": 5, "toplam_miktar": 6, "vergiler_dahil_tutar": 7,
        "para_birimi": 8, "kdv_haric_tutar": 9, "vergi_tutari": 10,
        "sirket_adi": 11, "vkn": 12, "vergi_dairesi": 13, "dosya": 14,
        "dosya_yolu_gizli": 15, "kaynak": 16,
    }


def test_her_sutun_numarasi_tek_bir_alana_ait():
    sutunlar = [a.sutun for a in ALANLAR]
    assert len(sutunlar) == len(set(sutunlar))


def test_form_alanlari_tablodan_turer():
    assert DUZENLENEBILIR_ALANLAR[0] == ("fatura_no", "Fatura No", "metin")
    assert {t for _, _, t in DUZENLENEBILIR_ALANLAR} <= {"metin", "tarih", "sayi"}
    # Formda görünen her alanın Excel'de de bir sütunu var.
    assert all(a in SUTUN for a, _, _ in DUZENLENEBILIR_ALANLAR)


def test_ogrenilen_alanlar_tablodan_turer():
    # para_birimi bilinçli olarak dışarıda: aynı firma TL/EUR kesebilir.
    assert OGRENILEN_ALANLAR == ["sirket_adi", "vergi_dairesi"]


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
