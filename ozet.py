# ozet.py
"""Özet sayfası için saf hesaplama mantığı (tkinter'sız, Excel'siz).

ozet_hesapla(satirlar) üç blok döner:
- genel : adet, para birimi bazında toplam tutar/KDV, kaynak dağılımı
- aylik : [("YYYY-AA" | "Bilinmiyor", {"adet", "tutar"})] kronolojik sıralı
- sirket: [(ad, {"adet", "tutar"})] toplam tutara göre azalan sıralı
"""
from collections import defaultdict
from datetime import date

from fatura import kaynak


def _para_birimi(s: dict) -> str:
    pb = str(s.get("para_birimi") or "").strip().upper()
    return pb or "TL"


def _tutar(s: dict):
    v = s.get("vergiler_dahil_tutar")
    return float(v) if isinstance(v, (int, float)) else None


def _kdv(s: dict):
    v, h = s.get("vergiler_dahil_tutar"), s.get("kdv_haric_tutar")
    if isinstance(v, (int, float)) and isinstance(h, (int, float)):
        return float(v) - float(h)
    return None


def _kaynak(s: dict) -> str:
    return kaynak(s, "Bilinmiyor")


def ozet_hesapla(satirlar: list[dict]) -> dict:
    """Fatura satırlarından genel/aylık/şirket özet yapısı üretir."""
    genel_tutar = defaultdict(float)
    genel_kdv = defaultdict(float)
    kaynak_sayim = defaultdict(int)
    aylik: dict[str, dict] = {}
    sirket: dict[str, dict] = {}

    for s in satirlar:
        pb, t, k = _para_birimi(s), _tutar(s), _kdv(s)
        if t is not None:
            genel_tutar[pb] += t
        if k is not None:
            genel_kdv[pb] += k
        kaynak_sayim[_kaynak(s)] += 1

        tarih = s.get("fatura_tarihi")
        # date kontrolü datetime'ı da kapsar (datetime, date alt sınıfı);
        # openpyxl bazı dosyalarda date dönebilir
        ay = (tarih.strftime("%Y-%m")
              if isinstance(tarih, date) else "Bilinmiyor")
        a = aylik.setdefault(ay, {"adet": 0, "tutar": defaultdict(float)})
        a["adet"] += 1
        if t is not None:
            a["tutar"][pb] += t

        ad = str(s.get("sirket_adi") or "").strip() or "Bilinmiyor"
        f = sirket.setdefault(ad, {"adet": 0, "tutar": defaultdict(float)})
        f["adet"] += 1
        if t is not None:
            f["tutar"][pb] += t

    ay_sirali = sorted(ay for ay in aylik if ay != "Bilinmiyor")
    if "Bilinmiyor" in aylik:
        ay_sirali.append("Bilinmiyor")
    # Not: farklı para birimleri kur çevirisi yapılmadan ham toplanır
    # (spec gereği) — karma para birimli veride sıralama yaklaşıktır.
    sirket_sirali = sorted(
        sirket, key=lambda ad: -sum(sirket[ad]["tutar"].values()))

    def _duz(blok):
        return {"adet": blok["adet"], "tutar": dict(blok["tutar"])}

    return {
        "genel": {"adet": len(satirlar), "tutar": dict(genel_tutar),
                  "kdv": dict(genel_kdv), "kaynak": dict(kaynak_sayim)},
        "aylik": [(ay, _duz(aylik[ay])) for ay in ay_sirali],
        "sirket": [(ad, _duz(sirket[ad])) for ad in sirket_sirali],
    }
