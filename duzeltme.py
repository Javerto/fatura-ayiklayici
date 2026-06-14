# duzeltme.py
"""Öğrenen düzeltme kuralları — firma-sabit alanlar için VKN bazlı kurallar.

Saf mantık (tkinter/Excel'siz, test edilebilir). Kurallar JSON'da tutulur:
    {"<vkn>": {"sirket_adi": "...", "vergi_dairesi": "..."}}
"""
import json

# Firma kimliğine ait, faturadan faturaya değişmeyen alanlar.
# para_birimi bilinçli olarak dışarıda: aynı firma TL/EUR kesebilir.
OGRENILEN_ALANLAR = ["sirket_adi", "vergi_dairesi"]


def kurallari_oku(yol) -> dict:
    """JSON kuralları oku; dosya yok/bozuksa boş sözlük döndür (çökme yok)."""
    try:
        with open(yol, "r", encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def kurallari_yaz(yol, kurallar: dict) -> None:
    """Kuralları JSON olarak yaz (UTF-8, okunabilir girinti)."""
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(kurallar, f, ensure_ascii=False, indent=2)


def kural_uygula(satir: dict, kurallar: dict) -> dict:
    """satır'ın vkn'si bir kuralla eşleşirse OGRENILEN_ALANLAR'ı geçersiz
    kılınmış bir KOPYA döndürür; eşleşme yoksa kopyayı olduğu gibi döndürür."""
    yeni = dict(satir)
    vkn = str(satir.get("vkn") or "").strip()
    kural = kurallar.get(vkn) if vkn else None
    if kural:
        for alan in OGRENILEN_ALANLAR:
            deger = kural.get(alan)
            if deger:
                yeni[alan] = deger
    return yeni


def kural_ekle(kurallar: dict, vkn: str, alanlar: dict) -> dict:
    """Yeni düzeltmeyi kurallara birleştirip güncel KOPYA döndürür.

    Boş/None değerler atlanır. vkn boşsa veya hiçbir öğrenilen alan dolu
    değilse kurallar (kopyası) değişmeden döner.
    """
    guncel = {k: dict(v) for k, v in kurallar.items()}
    vkn = str(vkn or "").strip()
    if not vkn:
        return guncel
    profil = dict(guncel.get(vkn, {}))
    for alan in OGRENILEN_ALANLAR:
        deger = alanlar.get(alan)
        if isinstance(deger, str):
            deger = deger.strip()
        if deger:
            profil[alan] = deger
    if profil:
        guncel[vkn] = profil
    return guncel
