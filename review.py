"""Onay/düzeltme arayüzünün saf mantığı (tkinter yok, test edilebilir)."""
from datetime import datetime

from extraction import to_float, tarih_parse
import sema as _sema
from fatura import DUZENLENEBILIR_ALANLAR, OGRENILEN_ALANLAR  # noqa: F401 (varsayılan şema; dışa açık)


def _metin(deger) -> str:
    """Bir alan değerini forma yazılacak metne çevirir."""
    if deger is None:
        return ""
    if isinstance(deger, datetime):
        return deger.strftime("%d.%m.%Y")
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger)


def satir_form_degerleri(row: dict, sema=None) -> dict:
    """Satırı, form alanlarına yazılacak metin değerlerine çevirir."""
    return {anahtar: _metin(row.get(anahtar))
            for anahtar, _, _ in (sema or _sema.VARSAYILAN).duzenlenebilir}


def nihai_satirlar(mevcut: list, yeni: list, haric: set) -> list:
    """Excel'e yazılacak nihai liste: mevcut satırlar + hariç tutulmayan yeniler."""
    dahil = [s for i, s in enumerate(yeni) if i not in haric]
    return list(mevcut) + dahil


def form_satira_uygula(row: dict, form: dict, sema=None) -> dict:
    """Form metinlerini tiplerine göre çevirip güncellenmiş satır KOPYASI döndürür.

    'sayi'  → to_float, 'tarih' → tarih_parse, 'metin' → strip (boşsa None).
    Düzenlenmeyen alanlar (dosya_yolu, _teknik_bilgi) korunur.
    """
    yeni = dict(row)
    for anahtar, _, tip in (sema or _sema.VARSAYILAN).duzenlenebilir:
        ham = (form.get(anahtar) or "").strip()
        if tip == "sayi":
            yeni[anahtar] = to_float(ham) if ham else None
        elif tip == "tarih":
            yeni[anahtar] = tarih_parse(ham) if ham else None
        else:
            yeni[anahtar] = ham or None
    return yeni


def ogrenilecek_alanlar(row: dict, sema=None) -> dict:
    """Satırdan öğrenilebilir (firma-sabit) alanların dolu olanlarını döndürür."""
    sonuc = {}
    for alan in (sema or _sema.VARSAYILAN).ogrenilen:
        deger = row.get(alan)
        if isinstance(deger, str):
            deger = deger.strip()
        if deger:
            sonuc[alan] = deger
    return sonuc
