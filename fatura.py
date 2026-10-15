"""Fatura satırının alan tablosu ve türetilen değerleri.

Bir fatura satırı hâlâ düz bir `dict` (bkz. CONTEXT.md); bu modül o dict'in
*varsayılan şemasını* (`sema.VARSAYILAN`) açar: `ALANLAR`, `SUTUN`,
`DUZENLENEBILIR_ALANLAR`, `OGRENILEN_ALANLAR`. Türetilen değerler (`kaynak`,
`dosya_adi`) da burada: aynı kural dört tüketicide kopyalanmıştı ve `ozet`teki
kopya sessizce ayrışmıştı ("Bilinmiyor").

`veri_dogrula`'nın alan adları bilinçli olarak şemanın dışında: alan başına
farklı bir kural — tabloya sıkıştırmak onu bozar.
"""
import os

# Alan tablosu artık bir veri dosyasından gelir (bkz. sema.py). Buradaki
# sabitler gömülü tohumdan türer; kullanıcının şemasıyla çalışan yollar
# `sema=` parametresiyle kendi şemalarını geçirir.
from sema import VARSAYILAN, Alan  # noqa: F401  (Alan dışarıya açık)

ALANLAR = VARSAYILAN.tum_alanlar

SUTUN = VARSAYILAN.sutun
DUZENLENEBILIR_ALANLAR = VARSAYILAN.duzenlenebilir
OGRENILEN_ALANLAR = VARSAYILAN.ogrenilen


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


def fatura_no_anahtari(satir: dict) -> str:
    """Mükerrer karşılaştırması için normalize edilmiş fatura no (boşsa "").

    Arşivin tekilliği bugün dosya adından geliyor (`mevcut_verileri_oku`);
    aynı fatura farklı adla klasöre düşerse o kontrol tutmuyor. Karşılaştırma
    büyük harfe çevrilir: Excel'den okunan eski satırlarla model çıktısı
    yalnızca harf büyüklüğünde ayrışabilir.
    """
    return str(satir.get("fatura_no") or "").strip().upper()


def dosya_adi(satir: dict, bos: str = "") -> str:
    """Kaynak dosyanın adı (yolsuz)."""
    return os.path.basename(str(satir.get("dosya_yolu") or "")) or bos
