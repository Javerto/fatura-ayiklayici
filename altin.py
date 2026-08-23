"""Altın küme: çıkarım doğruluğunu ölçen koşucu.

Testler mantığı koruyor ama *çıkarım kalitesini* ölçmüyordu; prompt ya da model
değiştiğinde "iyileşti mi" sorusunun cevabı yoktu. Bu betik elle doğrulanmış bir
fatura kümesini gerçek modele gönderip alan bazında doğruluk yüzdesi basar.

Kullanım:
    python altin.py                # rapor
    python altin.py --olustur      # eksik beklenen JSON'ları taslak olarak üret
    python altin.py --klasor D:\\altin

Klasör düzeni: her faturanın yanında aynı adlı `.json` (beklenen değerler).
Faturalar gizli veri olduğu için klasör `.gitignore`'da; repoya girmez.
Beklenen JSON'da yalnızca yazdığın alanlar karşılaştırılır — yarım doldurulmuş
bir altın satır da işe yarar.

Ağa çıkar ve API kotası harcar; bu yüzden pytest değil, elle çalıştırılan bir
betiktir.
"""

import argparse
import json
import os
import pathlib
import re
import sys

from dotenv import load_dotenv

import fatura
import gemini
from extraction import (pdf_den_veri_cek, xml_den_veri_cek, tarih_parse,
                        to_float)

VARSAYILAN_KLASOR = "altin"
ALAN_TIPI = {a.anahtar: a.tip for a in fatura.ALANLAR if a.tip}


# ─── Karşılaştırma ───────────────────────────────────────────────────────────

def _normalize(deger, tip):
    """Karşılaştırılabilir hale getirir: tarih → date, sayı → float, metin → sade."""
    if deger is None or deger == "":
        return None
    if tip == "sayi":
        return to_float(deger)
    if tip == "tarih":
        t = tarih_parse(deger)
        return t.date() if hasattr(t, "date") else str(t).strip()
    # Aynı işlem iki tarafa da uygulandığı için büyük harf dönüşümü yeterli;
    # amaç Türkçe kurallara uymak değil, iki metni aynı biçime getirmek.
    return re.sub(r"\s+", " ", str(deger)).strip().upper()


def esit(beklenen, bulunan, tip) -> bool:
    b, y = _normalize(beklenen, tip), _normalize(bulunan, tip)
    if tip == "sayi" and isinstance(b, float) and isinstance(y, float):
        return abs(b - y) <= 0.01      # kuruş farkı hata sayılmaz
    return b == y


def karsilastir(beklenen: dict, bulunan: dict) -> list[tuple[str, object, object]]:
    """Uyuşmayan alanlar: [(alan, beklenen, bulunan), ...]. Boş liste = tam isabet.

    Yalnızca beklenen JSON'da geçen alanlara bakılır.
    """
    fark = []
    for alan, bek in beklenen.items():
        tip = ALAN_TIPI.get(alan)
        if tip is None:                 # tanınmayan anahtar sessizce atlanmaz
            fark.append((alan, bek, "<bilinmeyen alan>"))
            continue
        if not esit(bek, bulunan.get(alan), tip):
            fark.append((alan, bek, bulunan.get(alan)))
    return fark


# ─── Koşu ────────────────────────────────────────────────────────────────────

def _faturalar(klasor: pathlib.Path) -> list[pathlib.Path]:
    return sorted(d for d in klasor.iterdir()
                  if d.suffix.lower() in (".pdf", ".xml"))


def _cikar(dosya: pathlib.Path, istemci) -> dict:
    if dosya.suffix.lower() == ".xml":
        return xml_den_veri_cek(str(dosya), None)
    return pdf_den_veri_cek(str(dosya), istemci)


def _istemci():
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY yok (.env veya ortam değişkeni).")
    return gemini.olustur(key, bilgi=lambda m: print(m))


def olustur(klasor: pathlib.Path):
    """Beklenen JSON taslaklarını modelden üretir — ELLE DÜZELTİLMELİ.

    Altın kümenin değeri insan doğrulamasından gelir; bu yalnızca 15 faturanın
    alanlarını sıfırdan yazma angaryasını kaldırır.
    """
    istemci = _istemci()
    for dosya in _faturalar(klasor):
        hedef = dosya.with_suffix(".json")
        if hedef.exists():
            print(f"atlandı (var): {hedef.name}")
            continue
        try:
            veri = _cikar(dosya, istemci)
        except Exception as e:
            print(f"HATA {dosya.name}: {type(e).__name__}: {e}")
            continue
        taslak = {a: veri.get(a) for a in ALAN_TIPI if veri.get(a) is not None}
        if hasattr(taslak.get("fatura_tarihi"), "strftime"):
            taslak["fatura_tarihi"] = taslak["fatura_tarihi"].strftime("%d.%m.%Y")
        hedef.write_text(json.dumps(taslak, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        print(f"yazıldı: {hedef.name}  ← GÖZDEN GEÇİR")


def rapor(klasor: pathlib.Path):
    istemci = _istemci()
    dosyalar = [d for d in _faturalar(klasor) if d.with_suffix(".json").exists()]
    if not dosyalar:
        sys.exit(f"{klasor} içinde beklenen JSON'u olan fatura yok "
                 f"(önce: python altin.py --olustur).")

    dogru, toplam = {}, {}
    hatalar = []
    tam_isabet = 0

    for dosya in dosyalar:
        beklenen = json.loads(dosya.with_suffix(".json").read_text(encoding="utf-8"))
        try:
            bulunan = _cikar(dosya, istemci)
        except Exception as e:
            hatalar.append((dosya.name, "—", f"{type(e).__name__}: {e}", ""))
            for alan in beklenen:
                toplam[alan] = toplam.get(alan, 0) + 1
            continue

        fark = dict((a, (b, y)) for a, b, y in karsilastir(beklenen, bulunan))
        for alan in beklenen:
            toplam[alan] = toplam.get(alan, 0) + 1
            if alan not in fark:
                dogru[alan] = dogru.get(alan, 0) + 1
        if fark:
            for alan, (b, y) in fark.items():
                hatalar.append((dosya.name, alan, b, y))
        else:
            tam_isabet += 1
        print(".", end="", flush=True)

    print("\n")
    # Model adı tabloya yazılır: iki koşunun çıktısı yan yana konacak, hangisinin
    # hangi modele ait olduğu hatırlanacak şey olmamalı.
    print(f"Model: {gemini.GEMMA_MODEL}   Fatura: {len(dosyalar)}")
    print(f"{'Alan':<22}{'Doğru':>7}{'Toplam':>8}{'%':>8}")
    print("-" * 45)
    for alan in ALAN_TIPI:
        if alan in toplam:
            d, t = dogru.get(alan, 0), toplam[alan]
            print(f"{alan:<22}{d:>7}{t:>8}{d / t * 100:>7.1f}")
    d, t = sum(dogru.values()), sum(toplam.values())
    print("-" * 45)
    print(f"{'GENEL':<22}{d:>7}{t:>8}{d / t * 100 if t else 0:>7.1f}")
    print(f"Tam isabetli fatura: {tam_isabet}/{len(dosyalar)}")

    if hatalar:
        print("\nUyuşmayanlar:")
        for ad, alan, bek, bul in hatalar:
            print(f"  {ad:<28} {alan:<20} bekl: {bek!r}  →  {bul!r}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Altın küme doğruluk raporu")
    p.add_argument("--klasor", default=VARSAYILAN_KLASOR)
    p.add_argument("--olustur", action="store_true",
                   help="Eksik beklenen JSON'ları modelden taslak olarak üret")
    p.add_argument("--model", help="A/B için model adı (varsayılan: gemini.GEMMA_MODEL)")
    a = p.parse_args(argv)

    if a.model:
        # PowerShell'de `VAR=deger komut` yok; ortam değişkenini kurcalamak
        # yerine sabiti burada değiştirmek yeterli (metin_uret çağrı anında okur).
        gemini.GEMMA_MODEL = a.model

    klasor = pathlib.Path(a.klasor)
    if not klasor.is_dir():
        sys.exit(f"Klasör yok: {klasor}")
    (olustur if a.olustur else rapor)(klasor)


if __name__ == "__main__":
    main()
