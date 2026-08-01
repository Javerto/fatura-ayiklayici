"""Fatura satırından türetilen değerler.

Bir fatura satırı hâlâ düz bir `dict` (bkz. CONTEXT.md). Bu modül yalnızca
o dict'ten *hesaplanan* alanları tek yerde tutar: aynı kural worker, api,
excel_utils ve ozet'te dört kez kopyalanmıştı ve ozet'teki kopya sessizce
ayrışmıştı ("Bilinmiyor").
"""
import os


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
