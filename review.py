"""Onay/düzeltme arayüzünün saf mantığı (tkinter yok, test edilebilir)."""
from datetime import datetime

from extraction import to_float, tarih_parse

# (anahtar, etiket, tip)  tip: "metin" | "tarih" | "sayi"
DUZENLENEBILIR_ALANLAR = [
    ("fatura_no",            "Fatura No",            "metin"),
    ("fatura_tarihi",        "Fatura Tarihi",        "tarih"),
    ("sirket_adi",           "Şirket Adı",           "metin"),
    ("vkn",                  "VKN",                  "metin"),
    ("vergi_dairesi",        "Vergi Dairesi",        "metin"),
    ("tanim",                "Tanım",                "metin"),
    ("toplam_miktar",        "Toplam Miktar",        "sayi"),
    ("kdv_haric_tutar",      "KDV Hariç Tutar",      "sayi"),
    ("vergiler_dahil_tutar", "Vergiler Dahil Tutar", "sayi"),
    ("para_birimi",          "Para Birimi",          "metin"),
    ("sira_no",              "Sıra No",              "sayi"),
]


def _metin(deger) -> str:
    """Bir alan değerini forma yazılacak metne çevirir."""
    if deger is None:
        return ""
    if isinstance(deger, datetime):
        return deger.strftime("%d.%m.%Y")
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger)


def satir_form_degerleri(row: dict) -> dict:
    """Satırı, form alanlarına yazılacak metin değerlerine çevirir."""
    return {anahtar: _metin(row.get(anahtar))
            for anahtar, _, _ in DUZENLENEBILIR_ALANLAR}


def nihai_satirlar(mevcut: list, yeni: list, haric: set) -> list:
    """Excel'e yazılacak nihai liste: mevcut satırlar + hariç tutulmayan yeniler."""
    dahil = [s for i, s in enumerate(yeni) if i not in haric]
    return list(mevcut) + dahil


def form_satira_uygula(row: dict, form: dict) -> dict:
    """Form metinlerini tiplerine göre çevirip güncellenmiş satır KOPYASI döndürür.

    'sayi'  → to_float, 'tarih' → tarih_parse, 'metin' → strip (boşsa None).
    Düzenlenmeyen alanlar (dosya_yolu, _teknik_bilgi) korunur.
    """
    yeni = dict(row)
    for anahtar, _, tip in DUZENLENEBILIR_ALANLAR:
        ham = (form.get(anahtar) or "").strip()
        if tip == "sayi":
            yeni[anahtar] = to_float(ham) if ham else None
        elif tip == "tarih":
            yeni[anahtar] = tarih_parse(ham) if ham else None
        else:
            yeni[anahtar] = ham or None
    return yeni
