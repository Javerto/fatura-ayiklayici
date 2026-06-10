# Tutar Tutarlılık Kontrolü + Özet Sayfası — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `veri_dogrula`'ya KDV matematiği kontrolü eklemek ve çıktı Excel'ine otomatik "Özet" sayfası (genel/aylık/şirket kırılımı) üretmek.

**Architecture:** Tutar kontrolü `extraction.py:veri_dogrula` içine saf bir blok olarak girer (worker + review penceresinde otomatik etkin). Özet hesabı yeni saf modül `ozet.py`'de (`ozet_hesapla`), Excel yazımı `excel_utils.py`'de `_ozet_sayfasi_yaz` yardımcı fonksiyonuyla `excel_olustur` içinden çağrılır. `excel_olustur` her seferinde sıfırdan `Workbook()` kurduğu için Özet sayfası çoğalamaz; ana sayfa ("Faturalar") ilk/aktif sayfa kalır. GUI/worker/review kodu değişmez.

**Tech Stack:** Python 3.14, openpyxl, pytest (TDD). Spec: `docs/superpowers/specs/2026-06-10-tutar-kontrolu-ve-ozet-sayfasi-design.md`

**Dil:** Tüm commit mesajları, yorumlar ve docstring'ler Türkçe.

---

### Task 1: Tutar tutarlılık kontrolü (`veri_dogrula`)

**Files:**
- Modify: `extraction.py` (≈ satır 186, `veri_dogrula`; modül sabitleri bölümüne `KDV_ORANLARI`)
- Test: `tests/test_tutar_kontrol.py` (yeni)

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_tutar_kontrol.py` (yeni dosya, tamamı):

```python
"""veri_dogrula tutar tutarlılık (örtük KDV oranı) testleri."""
from extraction import veri_dogrula


def _temiz_satir(**ek):
    """Tutar kontrolü dışındaki uyarıları tetiklemeyen taban satır."""
    s = {"fatura_no": "GIB2024123456789", "sirket_adi": "ACME",
         "vkn": "1234567890", "para_birimi": "TL"}
    s.update(ek)
    return s


def _tutar_uyarilari(satir):
    return [u for u in veri_dogrula(satir)
            if "KDV oranı" in u or "küçük" in u]


def test_yuzde20_kdv_uyari_yok():
    s = _temiz_satir(kdv_haric_tutar=100.0, vergiler_dahil_tutar=120.0)
    assert _tutar_uyarilari(s) == []


def test_dahil_haricten_kucuk_uyarir():
    s = _temiz_satir(kdv_haric_tutar=120.0, vergiler_dahil_tutar=100.0)
    uyarilar = _tutar_uyarilari(s)
    assert len(uyarilar) == 1
    assert "küçük" in uyarilar[0]


def test_sacma_oran_uyarir():
    s = _temiz_satir(kdv_haric_tutar=100.0, vergiler_dahil_tutar=137.0)
    uyarilar = _tutar_uyarilari(s)
    assert len(uyarilar) == 1
    assert "37" in uyarilar[0]          # %37.0 metinde geçmeli


def test_yuzde0_kdv_uyari_yok():
    s = _temiz_satir(kdv_haric_tutar=100.0, vergiler_dahil_tutar=100.0)
    assert _tutar_uyarilari(s) == []


def test_diger_gecerli_oranlar_uyari_yok():
    for oran in (1, 8, 10, 18, 20):
        s = _temiz_satir(kdv_haric_tutar=100.0,
                         vergiler_dahil_tutar=100.0 + oran)
        assert _tutar_uyarilari(s) == [], f"%{oran} yanlış alarm verdi"


def test_tolerans_kurus_yuvarlamasini_affeder():
    # 1234.56 * 1.20 = 1481.472 → 1481.47'ye yuvarlanmış (oran %19.9998…)
    s = _temiz_satir(kdv_haric_tutar=1234.56, vergiler_dahil_tutar=1481.47)
    assert _tutar_uyarilari(s) == []


def test_alan_bos_ise_kontrol_atlanir():
    assert _tutar_uyarilari(_temiz_satir(vergiler_dahil_tutar=120.0)) == []
    assert _tutar_uyarilari(_temiz_satir(kdv_haric_tutar=100.0)) == []
    assert _tutar_uyarilari(
        _temiz_satir(kdv_haric_tutar=0, vergiler_dahil_tutar=120.0)) == []
```

- [ ] **Step 2: Testlerin başarısız olduğunu doğrula**

Çalıştır: `python -m pytest tests/test_tutar_kontrol.py -q`
Beklenen: `test_dahil_haricten_kucuk_uyarir` ve `test_sacma_oran_uyarir` FAIL (uyarı üretilmiyor); diğerleri geçebilir.

- [ ] **Step 3: Minimal implementasyonu yaz**

`extraction.py` — modül sabitlerinin olduğu bölüme (örn. `_BILINEN_PARA_BIRIMLERI` tanımının yakınına) ekle:

```python
# Türkiye'de geçerli/yaygın KDV oranları (örtük oran kontrolü için)
KDV_ORANLARI = (0, 1, 8, 10, 18, 20)
```

`veri_dogrula` içinde, `# fatura_tarihi — parse edilememiş...` bloğundan ÖNCE
(mevcut `vergiler_dahil_tutar` bloğunun hemen ardına) ekle:

```python
    # tutar tutarlılığı — örtük KDV oranı bilinen oranlardan birine uymalı
    kht = veri.get("kdv_haric_tutar")
    if (isinstance(vdt, (int, float)) and isinstance(kht, (int, float))
            and vdt > 0 and kht > 0):
        if vdt < kht:
            uyarilar.append(
                f"Vergiler dahil tutar ({vdt}) KDV hariç tutardan ({kht}) küçük")
        else:
            oran = (vdt - kht) / kht * 100
            if not any(abs(oran - o) <= 0.5 for o in KDV_ORANLARI):
                uyarilar.append(
                    f"Örtük KDV oranı %{oran:.1f} bilinen oranlara "
                    f"(0/1/8/10/18/20) uymuyor — tutarları kontrol edin")
```

Not: `vdt` aynı fonksiyonda yukarıda zaten tanımlı (`veri.get("vergiler_dahil_tutar")`).

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Çalıştır: `python -m pytest tests/test_tutar_kontrol.py -q`
Beklenen: 7 passed.

- [ ] **Step 5: Tüm test paketini çalıştır (regresyon)**

Çalıştır: `python -m pytest -q`
Beklenen: tümü geçer (71 eski + 7 yeni = 78). Mevcut testlerde tutar çifti
kullanan satırlar varsa ve yeni uyarı üretiyorsa, test verisini %20 uyumlu
hale getir (örn. hariç=100, dahil=120) — uyarı metni beklentilerini bozmadan.

- [ ] **Step 6: Commit**

```bash
git add tests/test_tutar_kontrol.py extraction.py
git commit -m "feat: veri_dogrula'ya ortuk KDV orani tutarlilik kontrolu eklendi"
```

---

### Task 2: Saf özet hesabı (`ozet.py`)

**Files:**
- Create: `ozet.py`
- Test: `tests/test_ozet.py` (yeni)

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_ozet.py` (yeni dosya, tamamı):

```python
"""ozet.ozet_hesapla saf mantık testleri."""
from datetime import datetime

from ozet import ozet_hesapla


def _satir(**kw):
    s = {"fatura_no": "X", "sirket_adi": "ACME", "para_birimi": "TL",
         "fatura_tarihi": datetime(2024, 3, 15), "vergiler_dahil_tutar": 120.0,
         "kdv_haric_tutar": 100.0, "_teknik_bilgi": "Dijital",
         "dosya_yolu": "a.pdf"}
    s.update(kw)
    return s


def test_bos_liste():
    o = ozet_hesapla([])
    assert o["genel"]["adet"] == 0
    assert o["genel"]["tutar"] == {}
    assert o["aylik"] == []
    assert o["sirket"] == []


def test_genel_toplamlar_para_birimi_bazinda():
    satirlar = [
        _satir(),
        _satir(para_birimi="EUR", vergiler_dahil_tutar=50.0,
               kdv_haric_tutar=40.0),
        _satir(vergiler_dahil_tutar=240.0, kdv_haric_tutar=200.0),
    ]
    o = ozet_hesapla(satirlar)
    assert o["genel"]["adet"] == 3
    assert o["genel"]["tutar"] == {"TL": 360.0, "EUR": 50.0}
    assert o["genel"]["kdv"] == {"TL": 60.0, "EUR": 10.0}


def test_para_birimi_bos_tl_sayilir():
    o = ozet_hesapla([_satir(para_birimi=None)])
    assert o["genel"]["tutar"] == {"TL": 120.0}


def test_kdv_alani_eksik_kdv_toplamina_girmez():
    o = ozet_hesapla([_satir(kdv_haric_tutar=None)])
    assert o["genel"]["adet"] == 1
    assert o["genel"]["tutar"] == {"TL": 120.0}
    assert o["genel"]["kdv"] == {}


def test_kaynak_dagilimi():
    satirlar = [_satir(), _satir(_teknik_bilgi="OCR"),
                _satir(_teknik_bilgi=None, dosya_yolu="b.xml"),
                _satir(_teknik_bilgi=None, dosya_yolu=None)]
    o = ozet_hesapla(satirlar)
    assert o["genel"]["kaynak"] == {"Dijital": 1, "OCR": 1, "XML": 1,
                                    "Bilinmiyor": 1}


def test_aylik_kronolojik_ve_bilinmiyor_sonda():
    satirlar = [
        _satir(fatura_tarihi=datetime(2024, 5, 1)),
        _satir(fatura_tarihi=datetime(2024, 3, 1)),
        _satir(fatura_tarihi="okunamadi"),
        _satir(fatura_tarihi=datetime(2024, 3, 20),
               vergiler_dahil_tutar=240.0, kdv_haric_tutar=200.0),
    ]
    o = ozet_hesapla(satirlar)
    aylar = [ay for ay, _ in o["aylik"]]
    assert aylar == ["2024-03", "2024-05", "Bilinmiyor"]
    mart = dict(o["aylik"])["2024-03"]
    assert mart["adet"] == 2
    assert mart["tutar"] == {"TL": 360.0}


def test_sirket_tutara_gore_azalan():
    satirlar = [
        _satir(sirket_adi="Kucuk", vergiler_dahil_tutar=10.0,
               kdv_haric_tutar=None),
        _satir(sirket_adi="Buyuk", vergiler_dahil_tutar=1000.0,
               kdv_haric_tutar=None),
        _satir(sirket_adi=None, vergiler_dahil_tutar=5.0,
               kdv_haric_tutar=None),
    ]
    o = ozet_hesapla(satirlar)
    adlar = [ad for ad, _ in o["sirket"]]
    assert adlar == ["Buyuk", "Kucuk", "Bilinmiyor"]
    assert dict(o["sirket"])["Buyuk"]["tutar"] == {"TL": 1000.0}


def test_tutar_sayisal_degilse_adette_sayilir_toplama_girmez():
    o = ozet_hesapla([_satir(vergiler_dahil_tutar=None,
                             kdv_haric_tutar=None)])
    assert o["genel"]["adet"] == 1
    assert o["genel"]["tutar"] == {}
```

- [ ] **Step 2: Testlerin başarısız olduğunu doğrula**

Çalıştır: `python -m pytest tests/test_ozet.py -q`
Beklenen: FAIL — `ModuleNotFoundError: No module named 'ozet'`.

- [ ] **Step 3: `ozet.py` modülünü yaz**

`ozet.py` (yeni dosya, tamamı):

```python
# ozet.py
"""Özet sayfası için saf hesaplama mantığı (tkinter'sız, Excel'siz).

ozet_hesapla(satirlar) üç blok döner:
- genel : adet, para birimi bazında toplam tutar/KDV, kaynak dağılımı
- aylik : [("YYYY-AA" | "Bilinmiyor", {"adet", "tutar"})] kronolojik sıralı
- sirket: [(ad, {"adet", "tutar"})] toplam tutara göre azalan sıralı
"""
from collections import defaultdict
from datetime import datetime


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
    # excel_utils'teki Kaynak sütunu kuralıyla aynı: _teknik_bilgi öncelikli,
    # yoksa dosya uzantısından XML; ikisi de yoksa Bilinmiyor.
    tb = str(s.get("_teknik_bilgi") or "").strip()
    if tb:
        return tb
    if str(s.get("dosya_yolu") or "").lower().endswith(".xml"):
        return "XML"
    return "Bilinmiyor"


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
        ay = (tarih.strftime("%Y-%m")
              if isinstance(tarih, datetime) else "Bilinmiyor")
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
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Çalıştır: `python -m pytest tests/test_ozet.py -q`
Beklenen: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add ozet.py tests/test_ozet.py
git commit -m "feat: ozet.py — genel/aylik/sirket ozet hesabi (saf mantik)"
```

---

### Task 3: Excel "Özet" sayfası (`excel_utils`)

**Files:**
- Modify: `excel_utils.py` (`excel_olustur` sonu, `wb.save`den önce; yeni `_ozet_sayfasi_yaz`)
- Test: `tests/test_excel_ozet.py` (yeni)

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_excel_ozet.py` (yeni dosya, tamamı):

```python
"""Excel 'Özet' sayfası entegrasyon testleri."""
from datetime import datetime

from openpyxl import load_workbook

from excel_utils import excel_olustur, mevcut_verileri_oku


def _satirlar(tmp_path):
    return [
        {"fatura_no": "GIB2024123456789", "sirket_adi": "ACME",
         "fatura_tarihi": datetime(2024, 3, 15), "vergiler_dahil_tutar": 120.0,
         "kdv_haric_tutar": 100.0, "para_birimi": "TL", "vkn": "1234567890",
         "dosya_yolu": str(tmp_path / "a.pdf"), "_teknik_bilgi": "Dijital"},
        {"fatura_no": "ABC2024000000001", "sirket_adi": "Beta",
         "fatura_tarihi": datetime(2024, 4, 1), "vergiler_dahil_tutar": 50.0,
         "kdv_haric_tutar": 40.0, "para_birimi": "EUR", "vkn": "9876543210",
         "dosya_yolu": str(tmp_path / "b.xml"), "_teknik_bilgi": ""},
    ]


def test_ozet_sayfasi_olusur_ve_ana_sayfa_aktif_kalir(tmp_path):
    cikti = str(tmp_path / "c.xlsx")
    excel_olustur(_satirlar(tmp_path), cikti)
    wb = load_workbook(cikti)
    assert wb.sheetnames == ["Faturalar", "Özet"]
    assert wb.active.title == "Faturalar"
    ws = wb["Özet"]
    hucre_metinleri = [str(c.value) for row in ws.iter_rows()
                      for c in row if c.value is not None]
    assert "GENEL" in hucre_metinleri
    assert "AYLIK" in hucre_metinleri
    assert "ŞİRKET" in hucre_metinleri
    assert "Toplam Tutar (TL)" in hucre_metinleri
    assert "Toplam Tutar (EUR)" in hucre_metinleri
    wb.close()


def test_ozet_sayfali_dosyada_roundtrip_bozulmaz(tmp_path):
    cikti = str(tmp_path / "c.xlsx")
    excel_olustur(_satirlar(tmp_path), cikti)
    satirlar, islenmis = mevcut_verileri_oku(cikti)
    assert len(satirlar) == 2
    assert satirlar[0]["fatura_no"] == "GIB2024123456789"
    assert "a.pdf" in islenmis and "b.xml" in islenmis


def test_ikinci_yazimda_ozet_tek_kalir(tmp_path):
    cikti = str(tmp_path / "c.xlsx")
    excel_olustur(_satirlar(tmp_path), cikti)
    excel_olustur(_satirlar(tmp_path), cikti)
    wb = load_workbook(cikti)
    assert wb.sheetnames.count("Özet") == 1
    wb.close()


def test_bos_listede_ozet_sayfasi_yine_olusur(tmp_path):
    cikti = str(tmp_path / "c.xlsx")
    excel_olustur([], cikti)
    wb = load_workbook(cikti)
    assert "Özet" in wb.sheetnames
    wb.close()
```

- [ ] **Step 2: Testlerin başarısız olduğunu doğrula**

Çalıştır: `python -m pytest tests/test_excel_ozet.py -q`
Beklenen: ilk test FAIL (`sheetnames == ["Faturalar"]`, "Özet" yok).

- [ ] **Step 3: `_ozet_sayfasi_yaz` fonksiyonunu ekle**

`excel_utils.py` başına import ekle (mevcut importların altına):

```python
from ozet import ozet_hesapla
```

Dosyanın sonuna (modül seviyesinde, `excel_olustur`'dan sonra) ekle:

```python
def _ozet_sayfasi_yaz(wb, satirlar: list):
    """Çalışma kitabına 'Özet' sayfası ekler (genel/aylık/şirket blokları)."""
    o = ozet_hesapla(satirlar)
    ws = wb.create_sheet("Özet")

    baslik_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    baslik_fill = PatternFill("solid", start_color="2F5496")
    fbold = Font(name="Arial", bold=True, size=10)
    f10 = Font(name="Arial", size=10)
    num_fmt = "#,##0.00"

    r = 1

    def blok_baslik(metin):
        nonlocal r
        for col in range(1, 5):
            c = ws.cell(row=r, column=col)
            c.fill = baslik_fill
        c = ws.cell(row=r, column=1, value=metin)
        c.font, c.fill = baslik_font, baslik_fill
        r += 1

    def deger_satiri(etiket, deger, sayi=False):
        nonlocal r
        ws.cell(row=r, column=1, value=etiket).font = f10
        c = ws.cell(row=r, column=2, value=deger)
        c.font = f10
        if sayi:
            c.number_format = num_fmt
        r += 1

    # ── GENEL ──
    blok_baslik("GENEL")
    deger_satiri("Fatura Adedi", o["genel"]["adet"])
    for pb in sorted(o["genel"]["tutar"]):
        deger_satiri(f"Toplam Tutar ({pb})", o["genel"]["tutar"][pb], sayi=True)
    for pb in sorted(o["genel"]["kdv"]):
        deger_satiri(f"Toplam KDV ({pb})", o["genel"]["kdv"][pb], sayi=True)
    for kaynak in sorted(o["genel"]["kaynak"]):
        deger_satiri(f"Kaynak: {kaynak}", o["genel"]["kaynak"][kaynak])
    r += 1

    def kirilim_tablosu(baslik, ilk_kolon_adi, kayitlar):
        """kayitlar: [(ad, {"adet", "tutar": {pb: toplam}})]"""
        nonlocal r
        blok_baslik(baslik)
        for col, h in enumerate(
                [ilk_kolon_adi, "Adet", "Para Birimi", "Toplam Tutar"], 1):
            ws.cell(row=r, column=col, value=h).font = fbold
        r += 1
        for ad, v in kayitlar:
            pb_listesi = sorted(v["tutar"]) or [None]
            for i, pb in enumerate(pb_listesi):
                if i == 0:
                    ws.cell(row=r, column=1, value=ad).font = f10
                    ws.cell(row=r, column=2, value=v["adet"]).font = f10
                if pb is not None:
                    ws.cell(row=r, column=3, value=pb).font = f10
                    c = ws.cell(row=r, column=4, value=v["tutar"][pb])
                    c.font, c.number_format = f10, num_fmt
                r += 1
        r += 1

    kirilim_tablosu("AYLIK", "Ay", o["aylik"])
    kirilim_tablosu("ŞİRKET", "Şirket", o["sirket"])

    for col, w in [(1, 34), (2, 12), (3, 12), (4, 16)]:
        ws.column_dimensions[get_column_letter(col)].width = w
```

`excel_olustur` içinde `try: wb.save(cikti)` satırından hemen ÖNCE ekle:

```python
    _ozet_sayfasi_yaz(wb, satirlar)
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Çalıştır: `python -m pytest tests/test_excel_ozet.py -q`
Beklenen: 4 passed.

- [ ] **Step 5: Tüm test paketini çalıştır (regresyon)**

Çalıştır: `python -m pytest -q`
Beklenen: tümü geçer (Task 1-2 sonrası sayı + 4). Özellikle
`tests/test_excel_kaynak.py` ve `tests/test_worker.py` etkilenmemeli
(`mevcut_verileri_oku` `wb.active` okur; aktif sayfa "Faturalar" kalır).

- [ ] **Step 6: Commit**

```bash
git add excel_utils.py tests/test_excel_ozet.py
git commit -m "feat: cikti Excel'ine otomatik Ozet sayfasi (genel/aylik/sirket)"
```

---

### Task 4: Dokümantasyon + bütünleşik doğrulama

**Files:**
- Modify: `CLAUDE.md` (Module Responsibilities ve Data Flow bölümleri)

- [ ] **Step 1: CLAUDE.md'yi güncelle**

`CLAUDE.md` Module Responsibilities bölümüne, `excel_utils.py` maddesinin
içine/ardına şu bilgileri ekle (mevcut anlatımla uyumlu biçimde):

- `excel_utils.py` maddesine ekle: "Also writes an auto-generated **"Özet"
  sheet** (second sheet; general totals, monthly and company breakdowns,
  per-currency) via `_ozet_sayfasi_yaz`; the main "Faturalar" sheet stays
  first/active so older outputs and `mevcut_verileri_oku` are unaffected."
- Yeni madde: "**`ozet.py`** – Pure summary computation (`ozet_hesapla`):
  general/monthly/company breakdown with per-currency totals; no
  tkinter/openpyxl dependency."
- `extraction.py` maddesindeki `veri_dogrula` cümlesine ekle: "Includes an
  amount-consistency check: implied VAT rate from `kdv_haric_tutar` and
  `vergiler_dahil_tutar` must match a known Turkish VAT rate
  (`KDV_ORANLARI = (0, 1, 8, 10, 18, 20)`, ±0.5 tolerance)."

- [ ] **Step 2: Tüm testler + import dumanı**

Çalıştır: `python -m pytest -q` → tümü geçer.
Çalıştır: `python -c "import gui, worker, ozet, excel_utils; print('OK')"` → `OK`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: ozet.py modulu ve tutar tutarlilik kontrolu CLAUDE.md'ye eklendi"
```
