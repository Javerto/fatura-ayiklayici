"""Fatura satırının alan tablosu ve türetilen değerleri.

Bir fatura satırı hâlâ düz bir `dict` (bkz. CONTEXT.md); bu modül o dict'in
*şemasını* tutar. Alan listesi eskiden üç yere dağılmıştı (`excel_utils.SUTUN`,
`review.DUZENLENEBILIR_ALANLAR`, `duzeltme.OGRENILEN_ALANLAR`); üçü de artık
`ALANLAR`'dan türetilir. Türetilen değerler (`kaynak`, `dosya_adi`) da burada:
aynı kural dört tüketicide kopyalanmıştı ve `ozet`teki kopya sessizce
ayrışmıştı ("Bilinmiyor").

`PROMPT_SABLON` (extraction) ve `veri_dogrula`'nın alan adları bilinçli olarak
dışarıda: biri modele yazılmış Türkçe yönerge, diğeri alan başına farklı bir
kural — tabloya sıkıştırmak ikisini de bozar.
"""
import os
from typing import NamedTuple


class Alan(NamedTuple):
    """Bir fatura alanının Excel, form ve öğrenme tarafındaki karşılığı."""
    anahtar: str
    sutun: int                  # Excel sütun numarası (1 tabanlı)
    baslik: str | None = None   # Excel başlığı; None → başlıksız sütun
    genislik: int | None = None
    etiket: str | None = None   # form etiketi; None → formda düzenlenmez
    tip: str | None = None      # "metin" | "tarih" | "sayi"
    ogrenilir: bool = False     # VKN bazlı firma-sabit alan mı


# Sıra = gözden geçirme formundaki sıra. Excel sütun numaraları AÇIKÇA yazılır,
# listedeki sıradan türetilmez: eski Excel dosyaları o konumlardan okunuyor,
# listeyi yeniden sıralamak arşivi bozmamalı.
ALANLAR = [
    Alan("fatura_no",            2,  "Fatura No",            22, "Fatura No",            "metin"),
    Alan("fatura_tarihi",        3,  "Fatura Tarihi",        13, "Fatura Tarihi",        "tarih"),
    Alan("sirket_adi",           11, "Şirket Adı",           31, "Şirket Adı",           "metin", ogrenilir=True),
    Alan("vkn",                  12, "VKN",                  14, "VKN",                  "metin"),
    Alan("vergi_dairesi",        13, "Vergi Dairesi",        22, "Vergi Dairesi",        "metin", ogrenilir=True),
    Alan("tanim",                5,  "Tanım",                37, "Tanım",                "metin"),
    Alan("toplam_miktar",        6,  "Toplam Adet",          8,  "Toplam Miktar",        "sayi"),
    Alan("kdv_haric_tutar",      9,  "KDV Hariç Tutar",      16, "KDV Hariç Tutar",      "sayi"),
    Alan("vergiler_dahil_tutar", 7,  "Vergiler Dahil Tutar", 16, "Vergiler Dahil Tutar", "sayi"),
    Alan("para_birimi",          8,  "Para Birimi",          7,  "Para Birimi",          "metin"),
    Alan("sira_no",              4,  "Sıra No",              7,  "Sıra No",              "sayi"),
    # Formda yeri olmayan, Excel'e özel sütunlar
    Alan("ft_formul",            1,  "F+T",                  39),   # =fatura_no&tarih
    Alan("vergi_tutari",         10, "Vergi Tutarı",         16),   # =dahil-hariç
    Alan("dosya",                14, "Dosya",                12),   # hyperlink
    Alan("dosya_yolu_gizli",     15),                               # gizli tam yol
    Alan("kaynak",               16, "Kaynak",               9),
]

# Excel sütun numaraları: excel_utils buradan okur.
SUTUN = {a.anahtar: a.sutun for a in ALANLAR}

# Form alanları (anahtar, etiket, tip) — sıra formdaki sıradır.
DUZENLENEBILIR_ALANLAR = [(a.anahtar, a.etiket, a.tip) for a in ALANLAR if a.etiket]

# VKN bazlı öğrenilen, firma-sabit alanlar.
OGRENILEN_ALANLAR = [a.anahtar for a in ALANLAR if a.ogrenilir]


def kaynak(satir: dict, bilinmeyen: str = "") -> str:
    """Verinin nereden geldiği: Dijital / OCR / XML.

    `_teknik_bilgi` çıkarım sırasında yazılır (Dijital/OCR) ve Excel'den geri
    okunur; yoksa dosya uzantısından XML anlaşılır.
    """
    tb = str(satir.get("_teknik_bilgi") or "").strip()
    if tb:
        return tb
    if str(satir.get("dosya_yolu") or "").lower().endswith(".xml"):
        return "XML"
    return bilinmeyen


def dosya_adi(satir: dict, bos: str = "") -> str:
    """Kaynak dosyanın adı (yolsuz)."""
    return os.path.basename(str(satir.get("dosya_yolu") or "")) or bos
