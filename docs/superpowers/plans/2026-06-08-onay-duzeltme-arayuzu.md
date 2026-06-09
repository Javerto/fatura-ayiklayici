# Onay/Düzeltme Arayüzü Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Excel yazılmadan önce çıkarılan faturaları master-detail bir pencerede gözden geçirip düzeltme, hariç tutma ve kaynak PDF'i önizleme imkânı eklemek.

**Architecture:** Saf mantık (`review.py`) ile arayüz (`review_ui.py`) ayrılır. `worker.py` artık Excel yazmaz; bitince `("review", payload)` yayınlar. `gui.py` onay penceresini açar ve onayda `excel_olustur` çağırır.

**Tech Stack:** Python 3, tkinter/ttk, PyMuPDF (`fitz`) PDF render, openpyxl (mevcut), pytest.

**Referans spec:** `docs/superpowers/specs/2026-06-08-onay-duzeltme-arayuzu-design.md`

---

## Dosya Yapısı

- **Create** `review.py` — saf mantık: `DUZENLENEBILIR_ALANLAR`, `satir_form_degerleri`, `form_satira_uygula`, `nihai_satirlar`.
- **Create** `review_ui.py` — `ReviewWindow` sınıfı (tablo + form + PDF önizleme).
- **Create** `tests/test_review.py` — `review.py` birim testleri.
- **Modify** `worker.py` — Excel yazımını kaldır, `yeni_satirlar` topla, `("review", payload)` yayınla.
- **Modify** `tests/test_worker.py` — yeni sözleşmeye göre güncelle.
- **Modify** `gui.py` — `_poll_queue`'da `"review"` kolu, `_islem_bitti` çıkarımı, onay/iptal geri çağırımları.

---

## Task 1: review.py — alan tanımı + satir_form_degerleri

**Files:**
- Create: `review.py`
- Test: `tests/test_review.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_review.py
"""review.py saf mantık testleri."""
from datetime import datetime

import pytest

from review import (DUZENLENEBILIR_ALANLAR, satir_form_degerleri)


def test_form_degerleri_tarih_ve_sayi_metne_cevrilir():
    row = {"fatura_no": "GIB2024123456789", "fatura_tarihi": datetime(2024, 3, 15),
           "toplam_miktar": 5.0, "vergiler_dahil_tutar": 1180.0,
           "sira_no": None, "para_birimi": "TL"}
    f = satir_form_degerleri(row)
    assert f["fatura_tarihi"] == "15.03.2024"
    assert f["toplam_miktar"] == "5"          # tam sayı float → ondalıksız
    assert f["vergiler_dahil_tutar"] == "1180"
    assert f["sira_no"] == ""                 # None → boş
    assert f["para_birimi"] == "TL"


def test_form_degerleri_tum_alanlar_string_ve_eksiksiz():
    f = satir_form_degerleri({})
    assert set(f.keys()) == {a for a, _, _ in DUZENLENEBILIR_ALANLAR}
    assert all(isinstance(v, str) for v in f.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'review'`

- [ ] **Step 3: Write minimal implementation**

```python
# review.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add review.py tests/test_review.py
git commit -m "feat: review.py alan tanımı ve satir_form_degerleri"
```

---

## Task 2: review.py — form_satira_uygula

**Files:**
- Modify: `review.py`
- Test: `tests/test_review.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_review.py — dosyanın sonuna ekle
from review import form_satira_uygula


def _bos_form():
    return {a: "" for a, _, _ in DUZENLENEBILIR_ALANLAR}


def test_uygula_sayi_ve_tarih_cevirir():
    form = {**_bos_form(),
            "fatura_no": "GIB2024123456789", "fatura_tarihi": "15.03.2024",
            "vergiler_dahil_tutar": "1.234,56", "toplam_miktar": "5",
            "sirket_adi": "ACME", "vkn": "1234567890"}
    y = form_satira_uygula({"dosya_yolu": "x.pdf"}, form)
    assert y["vergiler_dahil_tutar"] == 1234.56
    assert y["fatura_tarihi"] == datetime(2024, 3, 15)
    assert y["toplam_miktar"] == 5.0
    assert y["sira_no"] is None              # boş sayı → None
    assert y["dosya_yolu"] == "x.pdf"        # düzenlenmeyen alan korunur


def test_uygula_gecersiz_tarih_metin_kalir():
    y = form_satira_uygula({}, {**_bos_form(), "fatura_tarihi": "abc"})
    assert y["fatura_tarihi"] == "abc"


def test_uygula_orijinal_satiri_bozmaz():
    row = {"fatura_no": "ESKI"}
    form_satira_uygula(row, {**_bos_form(), "fatura_no": "YENI"})
    assert row["fatura_no"] == "ESKI"        # kopya döner, mutasyon yok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -q`
Expected: FAIL — `ImportError: cannot import name 'form_satira_uygula'`

- [ ] **Step 3: Write minimal implementation**

```python
# review.py — _metin/satir_form_degerleri'den sonra ekle
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add review.py tests/test_review.py
git commit -m "feat: form_satira_uygula — form metnini tipli değere çevirir"
```

---

## Task 3: review.py — nihai_satirlar + yeniden doğrulama kapanışı

**Files:**
- Modify: `review.py`
- Test: `tests/test_review.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_review.py — dosyanın sonuna ekle
from review import nihai_satirlar
from extraction import veri_dogrula


def test_nihai_satirlar_haric_tutulanlari_cikarir():
    mevcut = [{"fatura_no": "M"}]
    yeni = [{"fatura_no": "A"}, {"fatura_no": "B"}, {"fatura_no": "C"}]
    sonuc = nihai_satirlar(mevcut, yeni, {1})
    assert [s["fatura_no"] for s in sonuc] == ["M", "A", "C"]


def test_nihai_satirlar_bos_haric():
    assert nihai_satirlar([], [{"x": 1}], set()) == [{"x": 1}]


def test_revalidation_kapanisi_vkn_duzeltince_uyari_kalkar():
    row = {"fatura_no": "GIB2024123456789", "vergiler_dahil_tutar": 100.0,
           "para_birimi": "TL", "sirket_adi": "ACME",
           "fatura_tarihi": datetime(2024, 1, 1), "vkn": "123"}
    assert any("VKN" in u for u in veri_dogrula(row))
    duzeltilmis = form_satira_uygula(
        row, {**satir_form_degerleri(row), "vkn": "1234567890"})
    assert not any("VKN" in u for u in veri_dogrula(duzeltilmis))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -q`
Expected: FAIL — `ImportError: cannot import name 'nihai_satirlar'`

- [ ] **Step 3: Write minimal implementation**

```python
# review.py — dosyanın sonuna ekle
def nihai_satirlar(mevcut: list, yeni: list, haric: set) -> list:
    """Excel'e yazılacak nihai liste: mevcut satırlar + hariç tutulmayan yeniler."""
    dahil = [s for i, s in enumerate(yeni) if i not in haric]
    return list(mevcut) + dahil
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add review.py tests/test_review.py
git commit -m "feat: nihai_satirlar + yeniden doğrulama kapanış testi"
```

---

## Task 4: worker.py — Excel yazımını ertele, "review" yayınla

**Files:**
- Modify: `worker.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Update the test to the new contract**

`tests/test_worker.py` içindeki `test_worker_xml_only_excel_olusturur` fonksiyonunu **tamamen** şu fonksiyonla değiştir:

```python
def test_worker_xml_only_review_yayinlar(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "fatura1.xml")
    log_q = queue.Queue()
    stop = threading.Event()

    worker("FAKE_KEY", str(tmp_path), "cikti.xlsx", log_q, stop)

    mesajlar = _kuyrugu_bosalt(log_q)
    tipler = [t for t, _ in mesajlar]
    assert "review" in tipler
    assert "done" not in tipler        # yeni satır var → review, done değil

    payload = next(d for t, d in mesajlar if t == "review")
    assert len(payload["yeni"]) == 1
    assert payload["atlanmis"] == []
    assert payload["kesildi"] is False

    # Worker ARTIK Excel yazmaz — yazım onaya ertelendi
    assert not (tmp_path / "cikti.xlsx").exists()
```

`test_worker_bos_klasor_uyari_verir` aynen kalır.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_worker.py -q`
Expected: FAIL — `test_worker_xml_only_review_yayinlar`: "review" not in tipler (worker hâlâ "done" yayınlıyor ve Excel yazıyor).

- [ ] **Step 3: Update worker.py — import**

`worker.py` içindeki import satırını değiştir:

```python
# ESKİ:
from excel_utils import mevcut_verileri_oku, excel_olustur, ExcelHatasi
# YENİ:
from excel_utils import mevcut_verileri_oku
```

- [ ] **Step 4: Update worker.py — sayaç/liste kurulumu, islendi, _bitir**

`worker.py` içinde şu bloğu:

```python
    satirlar = list(mevcut_satirlar)
    atlanmis      = []
    uyari_listesi = []   # [(dosya_adi, [uyari, ...]), ...]
    yeni     = 0
    siradaki = 0

    def islendi(veri):
        nonlocal yeni, siradaki
        satirlar.append(veri)
        yeni += 1
        siradaki += 1
        log_q.put(("progress", (siradaki, toplam)))
        tutar = veri.get("vergiler_dahil_tutar")
        tutar_str = f"{tutar:,.2f} {veri.get('para_birimi', 'TL')}" if tutar else "-"
        log("ok", f"✓  {(veri.get('fatura_no') or '-'):<20} "
                  f"{(veri.get('sirket_adi') or '-')[:25]:<26} {tutar_str}")
        uyarilar = veri_dogrula(veri)
        for u in uyarilar:
            log("warn", f"   ⚠ {u}")
        if uyarilar:
            dosya_adi = os.path.basename(veri.get("dosya_yolu") or
                                         veri.get("xml_yolu") or "bilinmiyor")
            uyari_listesi.append((dosya_adi, uyarilar))
        if yeni % 5 == 0:
            try:
                excel_olustur(satirlar, CIKTI)
            except ExcelHatasi as e:
                log("warn", f"   ⚠ Kayıt başarısız: {e}")
```

şununla değiştir:

```python
    yeni_satirlar = []
    atlanmis      = []
    uyari_listesi = []   # [(dosya_adi, [uyari, ...]), ...]
    siradaki = 0

    def islendi(veri):
        nonlocal siradaki
        yeni_satirlar.append(veri)
        siradaki += 1
        log_q.put(("progress", (siradaki, toplam)))
        tutar = veri.get("vergiler_dahil_tutar")
        tutar_str = f"{tutar:,.2f} {veri.get('para_birimi', 'TL')}" if tutar else "-"
        log("ok", f"✓  {(veri.get('fatura_no') or '-'):<20} "
                  f"{(veri.get('sirket_adi') or '-')[:25]:<26} {tutar_str}")
        uyarilar = veri_dogrula(veri)
        for u in uyarilar:
            log("warn", f"   ⚠ {u}")
        if uyarilar:
            dosya_adi = os.path.basename(veri.get("dosya_yolu") or "bilinmiyor")
            uyari_listesi.append((dosya_adi, uyarilar))

    def _bitir(kesildi=False):
        """İşlem sonu: yeni satır varsa onaya gönder, yoksa done yayınla."""
        if yeni_satirlar:
            log_q.put(("review", {
                "mevcut":   mevcut_satirlar,
                "yeni":     yeni_satirlar,
                "atlanmis": atlanmis,
                "uyarilar": uyari_listesi,
                "cikti":    CIKTI,
                "kesildi":  kesildi,
            }))
        else:
            log("info", "Kaydedilecek yeni fatura bulunamadı.")
            log_q.put(("done", (atlanmis, 0, uyari_listesi)))
```

- [ ] **Step 5: Update worker.py — kritik (API-key) abort yolu**

Şu bloğu:

```python
                elif tip == "critical":
                    log("critical", str(veri))
                    for f in bekleyen:
                        f.cancel()
                    log_q.put(("done", (atlanmis, yeni, uyari_listesi)))
                    return
```

şununla değiştir:

```python
                elif tip == "critical":
                    log("critical", str(veri))
                    for f in bekleyen:
                        f.cancel()
                    _bitir(kesildi=True)
                    return
```

- [ ] **Step 6: Update worker.py — final blok**

Dosyanın sonundaki şu bloğu:

```python
    # ── Final Excel kaydı ──────────────────────────────────────────────
    if satirlar:
        try:
            excel_olustur(satirlar, CIKTI)
            log("done_ok", f"Excel oluşturuldu: {CIKTI}  ({len(satirlar)} fatura, {yeni} yeni)")
        except ExcelHatasi as e:
            log("critical", str(e))
    else:
        log("info", "İşlenebilecek fatura bulunamadı.")

    log_q.put(("done", (atlanmis, yeni, uyari_listesi)))
```

şununla değiştir:

```python
    # ── İşlem sonu: onaya gönder ───────────────────────────────────────
    _bitir(kesildi=stop_event.is_set())
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py -q`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add worker.py tests/test_worker.py
git commit -m "feat: worker Excel yazmaz, bitince review payload yayınlar"
```

---

## Task 5: review_ui.py — ReviewWindow (tablo + form + butonlar, önizleme placeholder)

**Files:**
- Create: `review_ui.py`

> Bu sınıf tkinter penceresidir; otomatik birim test yerine kurulum smoke testi ile doğrulanır (Step 2-3).

- [ ] **Step 1: Write the module**

```python
# review_ui.py
"""Onay/düzeltme penceresi (ReviewWindow)."""
import base64
import os
import tkinter as tk
from tkinter import ttk, messagebox

import fitz

from extraction import veri_dogrula
from review import (DUZENLENEBILIR_ALANLAR, satir_form_degerleri,
                    form_satira_uygula, nihai_satirlar)


class ReviewWindow:
    """Çıkarılan yeni faturaları gözden geçirme/düzeltme penceresi.

    on_confirm(nihai_satirlar, guncel_uyarilar) -> bool
        True dönerse pencere kapanır (yazım başarılı), False ise açık kalır.
    on_cancel() -> None
    """

    def __init__(self, parent, payload, palet, on_confirm, on_cancel):
        self.parent = parent
        self.mevcut = payload["mevcut"]
        self.yeni = payload["yeni"]
        self.atlanmis = payload["atlanmis"]
        self.cikti = payload["cikti"]
        self.kesildi = payload.get("kesildi", False)
        self.p = palet
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel

        self.haric = set()
        self.secili = None
        self.uyari = [veri_dogrula(s) for s in self.yeni]
        self.form_vars = {}

        # önizleme durumu (Task 6'da kullanılır)
        self._pdf_doc = None
        self._pdf_yol = None
        self._tk_img = None
        self.zoom = 1.5
        self.sayfa = 0

        self._build()
        self._tabloyu_doldur()
        self._ilk_uyariliyi_sec()

    # ── UI kurulumu ──
    def _build(self):
        p = self.p
        self.win = tk.Toplevel(self.parent)
        self.win.title("Faturaları Gözden Geçir")
        self.win.configure(bg=p["BG"])
        self.win.transient(self.parent)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._iptal)

        toplam_u = sum(len(u) for u in self.uyari)
        baslik = f"{len(self.yeni)} yeni fatura, {toplam_u} uyarı"
        if self.kesildi:
            baslik += "  (işlem yarıda kesildi)"
        tk.Label(self.win, text=baslik, font=("Arial", 12, "bold"),
                 bg=p["MANTLE"], fg=p["BLUE"]).pack(fill="x", ipady=8)

        # Özet tablo
        tablo_frame = tk.Frame(self.win, bg=p["BG"])
        tablo_frame.pack(fill="x", padx=10, pady=(8, 4))
        kolonlar = ("fatura_no", "sirket_adi", "tutar", "kaynak", "uyari")
        self.tree = ttk.Treeview(tablo_frame, columns=kolonlar,
                                 show="headings", height=7)
        for k, b, w in [("fatura_no", "Fatura No", 160), ("sirket_adi", "Şirket", 210),
                        ("tutar", "Tutar", 90), ("kaynak", "Kaynak", 70),
                        ("uyari", "⚠", 40)]:
            self.tree.heading(k, text=b)
            self.tree.column(k, width=w, anchor="w")
        self.tree.tag_configure("uyari", background="#3a3a2a", foreground="#f9e2af")
        self.tree.tag_configure("haric", foreground=p["OVERLAY"])
        sb = ttk.Scrollbar(tablo_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._satir_secildi)

        # Orta: form (sol) + önizleme (sağ)
        orta = tk.Frame(self.win, bg=p["BG"])
        orta.pack(fill="both", expand=True, padx=10, pady=4)

        form_frame = tk.LabelFrame(orta, text=" Düzenle ", bg=p["MANTLE"],
                                   fg=p["SUBTEXT"], padx=6, pady=6)
        form_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        for satir, (anahtar, etiket, _tip) in enumerate(DUZENLENEBILIR_ALANLAR):
            tk.Label(form_frame, text=etiket + ":", bg=p["MANTLE"], fg=p["TEXT"],
                     font=("Arial", 9), anchor="w", width=16
                     ).grid(row=satir, column=0, sticky="w", padx=4, pady=2)
            var = tk.StringVar()
            self.form_vars[anahtar] = var
            tk.Entry(form_frame, textvariable=var, width=28, font=("Arial", 9),
                     bg=p["SURFACE"], fg=p["TEXT"], insertbackground=p["TEXT"],
                     relief="flat").grid(row=satir, column=1, sticky="ew",
                                         padx=(0, 4), pady=2)
        self.uyari_label = tk.Label(form_frame, text="", bg=p["MANTLE"], fg=p["RED"],
                                    font=("Arial", 8), justify="left", anchor="w",
                                    wraplength=320)
        self.uyari_label.grid(row=len(DUZENLENEBILIR_ALANLAR), column=0,
                              columnspan=2, sticky="w", padx=4, pady=(6, 2))
        tk.Button(form_frame, text="Uygula", command=self._uygula,
                  bg=p["SURFACE"], fg=p["GREEN"], relief="flat", padx=12,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["GREEN"]
                  ).grid(row=len(DUZENLENEBILIR_ALANLAR) + 1, column=0,
                         columnspan=2, pady=6)
        form_frame.columnconfigure(1, weight=1)

        self.onizleme_frame = tk.LabelFrame(orta, text=" Önizleme ", bg=p["MANTLE"],
                                            fg=p["SUBTEXT"], padx=6, pady=6)
        self.onizleme_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        self._onizleme_kur()

        # Alt buton çubuğu
        alt = tk.Frame(self.win, bg=p["BG"])
        alt.pack(fill="x", padx=10, pady=(4, 10))
        self.haric_var = tk.BooleanVar(value=False)
        tk.Checkbutton(alt, text="Bu faturayı hariç tut", variable=self.haric_var,
                       command=self._haric_degisti, bg=p["BG"], fg=p["TEXT"],
                       selectcolor=p["SURFACE"], activebackground=p["BG"],
                       font=("Arial", 9)).pack(side="left")
        tk.Button(alt, text="◀ Önceki ⚠", command=lambda: self._uyariliya_atla(-1),
                  bg=p["SURFACE"], fg=p["SUBTEXT"], relief="flat", padx=8,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["TEXT"]).pack(side="left", padx=(12, 2))
        tk.Button(alt, text="Sonraki ⚠ ▶", command=lambda: self._uyariliya_atla(1),
                  bg=p["SURFACE"], fg=p["SUBTEXT"], relief="flat", padx=8,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["TEXT"]).pack(side="left", padx=2)
        tk.Button(alt, text="Onayla & Excel", command=self._onayla,
                  bg=p["SURFACE"], fg=p["GREEN"], relief="flat", padx=14,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["GREEN"]).pack(side="right")
        tk.Button(alt, text="İptal", command=self._iptal,
                  bg=p["SURFACE"], fg=p["RED"], relief="flat", padx=14,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["RED"]).pack(side="right", padx=(0, 8))

    # ── Tablo ──
    def _tabloyu_doldur(self):
        self.tree.delete(*self.tree.get_children())
        for i in range(len(self.yeni)):
            self.tree.insert("", "end", iid=str(i),
                             values=self._satir_degerleri(i), tags=self._satir_tag(i))

    def _satir_degerleri(self, i):
        s = self.yeni[i]
        tutar = s.get("vergiler_dahil_tutar")
        tutar_str = f"{tutar:,.2f}" if isinstance(tutar, (int, float)) else "-"
        kaynak = s.get("_teknik_bilgi") or (
            "XML" if str(s.get("dosya_yolu", "")).lower().endswith(".xml") else "")
        u = len(self.uyari[i])
        return (s.get("fatura_no") or "-", (s.get("sirket_adi") or "-")[:32],
                tutar_str, kaynak, str(u) if u else "-")

    def _satir_tag(self, i):
        if i in self.haric:
            return ("haric",)
        return ("uyari",) if self.uyari[i] else ()

    def _tabloyu_guncelle(self, i):
        self.tree.item(str(i), values=self._satir_degerleri(i), tags=self._satir_tag(i))

    # ── Seçim / form ──
    def _satir_secildi(self, _event=None):
        sec = self.tree.selection()
        if not sec:
            return
        i = int(sec[0])
        self.secili = i
        degerler = satir_form_degerleri(self.yeni[i])
        for anahtar, var in self.form_vars.items():
            var.set(degerler.get(anahtar, ""))
        self.haric_var.set(i in self.haric)
        self._uyari_goster(i)
        self._onizleme_yukle(self.yeni[i].get("dosya_yolu"))

    def _uyari_goster(self, i):
        uy = self.uyari[i]
        self.uyari_label.config(text="\n".join("⚠ " + u for u in uy) if uy else "")

    def _uygula(self):
        if self.secili is None:
            return
        i = self.secili
        form = {a: v.get() for a, v in self.form_vars.items()}
        self.yeni[i] = form_satira_uygula(self.yeni[i], form)
        self.uyari[i] = veri_dogrula(self.yeni[i])
        self._uyari_goster(i)
        self._tabloyu_guncelle(i)

    def _haric_degisti(self):
        if self.secili is None:
            return
        i = self.secili
        if self.haric_var.get():
            self.haric.add(i)
        else:
            self.haric.discard(i)
        self._tabloyu_guncelle(i)

    def _sec(self, i):
        self.tree.selection_set(str(i))
        self.tree.see(str(i))

    def _ilk_uyariliyi_sec(self):
        for i in range(len(self.yeni)):
            if self.uyari[i]:
                self._sec(i)
                return
        if self.yeni:
            self._sec(0)

    def _uyariliya_atla(self, yon):
        n = len(self.yeni)
        if not n:
            return
        bas = self.secili if self.secili is not None else 0
        for adim in range(1, n + 1):
            j = (bas + yon * adim) % n
            if self.uyari[j]:
                self._sec(j)
                return

    # ── Önizleme (Task 6'da gerçek render ile değiştirilecek) ──
    def _onizleme_kur(self):
        self.onizleme_label = tk.Label(self.onizleme_frame, text="Önizleme yok",
                                       bg=self.p["MANTLE"], fg=self.p["SUBTEXT"])
        self.onizleme_label.pack(fill="both", expand=True)

    def _onizleme_yukle(self, yol):
        self.onizleme_label.config(
            text=os.path.basename(yol) if yol else "Önizleme yok")

    # ── Onay / İptal ──
    def _onayla(self):
        kalan = sum(1 for i in range(len(self.yeni))
                    if i not in self.haric and self.uyari[i])
        if kalan and not messagebox.askyesno(
                "Uyarılar var",
                f"{kalan} faturada hâlâ uyarı var. Yine de Excel'e yazılsın mı?"):
            return
        nihai = nihai_satirlar(self.mevcut, self.yeni, self.haric)
        guncel_uyarilar = [
            (os.path.basename(self.yeni[i].get("dosya_yolu") or "bilinmiyor"),
             self.uyari[i])
            for i in range(len(self.yeni)) if i not in self.haric and self.uyari[i]]
        if self.on_confirm(nihai, guncel_uyarilar):
            self.win.destroy()

    def _iptal(self):
        if messagebox.askyesno(
                "İptal",
                "Çıkarılan veriler ve düzeltmeler kaydedilmeyecek. Emin misiniz?"):
            self.win.destroy()
            self.on_cancel()
```

- [ ] **Step 2: Write a construction smoke script**

`_smoke_review.py` (geçici dosya):

```python
"""ReviewWindow kurulum smoke testi: pencereyi kur, render et, ekran görüntüsü al."""
import os, tkinter as tk
from datetime import datetime
from PIL import ImageGrab
from review_ui import ReviewWindow

PALET = {"BG": "#1e1e2e", "MANTLE": "#181825", "SURFACE": "#313244",
         "TEXT": "#cdd6f4", "SUBTEXT": "#a6adc8", "BLUE": "#89b4fa",
         "GREEN": "#a6e3a1", "RED": "#f38ba8", "OVERLAY": "#6c7086"}

payload = {
    "mevcut": [],
    "yeni": [
        {"fatura_no": "GIB2024000000123", "sirket_adi": "ACME A.S.",
         "vergiler_dahil_tutar": 1180.0, "para_birimi": "TL",
         "fatura_tarihi": datetime(2024, 3, 15), "vkn": "1234567890",
         "_teknik_bilgi": "Dijital", "dosya_yolu": r"C:\yok\a.pdf"},
        {"fatura_no": "ABC2024000000777", "sirket_adi": "Eski Matbaa",
         "vergiler_dahil_tutar": 590.0, "para_birimi": "TL",
         "fatura_tarihi": "okunamadi", "vkn": "123",
         "_teknik_bilgi": "OCR", "dosya_yolu": r"C:\yok\b.pdf"},
    ],
    "atlanmis": [], "uyarilar": [], "cikti": "x.xlsx", "kesildi": False,
}

root = tk.Tk(); root.withdraw()
rw = ReviewWindow(root, payload, PALET, lambda n, u: True, lambda: None)
rw.win.lift(); rw.win.attributes("-topmost", True)
root.update_idletasks(); root.update()
x, y = rw.win.winfo_rootx(), rw.win.winfo_rooty()
w, h = rw.win.winfo_width(), rw.win.winfo_height()
out = os.path.join(os.environ.get("TEMP", "."), "review_smoke.png")
ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out)
print("OK", w, "x", h, "->", out)
root.destroy()
```

- [ ] **Step 3: Run smoke and view screenshot**

Run: `python _smoke_review.py`
Expected: `OK <w> x <h> -> ...review_smoke.png` (hata yok). Ekran görüntüsünü aç ve tablo+form+butonların göründüğünü, ikinci satırın (uyarılı) sarı vurgulandığını doğrula. Sonra `rm _smoke_review.py`.

- [ ] **Step 4: Run full test suite (regresyon)**

Run: `python -m pytest -q`
Expected: PASS (tümü yeşil)

- [ ] **Step 5: Commit**

```bash
git add review_ui.py
git commit -m "feat: ReviewWindow — master-detail tablo, form, hariç tut, uyarıya atla"
```

---

## Task 6: review_ui.py — gömülü PDF önizleme + zoom/sayfa/dışarıda aç

**Files:**
- Modify: `review_ui.py`

- [ ] **Step 1: Replace the preview methods**

`review_ui.py` içindeki `_onizleme_kur` ve `_onizleme_yukle` metotlarını **tamamen** şu beş metotla değiştir:

```python
    # ── Önizleme (gömülü PDF render) ──
    def _onizleme_kur(self):
        p = self.p
        self.onizleme_label = tk.Label(self.onizleme_frame, text="Önizleme yok",
                                       bg=p["MANTLE"], fg=p["SUBTEXT"])
        self.onizleme_label.pack(fill="both", expand=True)
        kontrol = tk.Frame(self.onizleme_frame, bg=p["MANTLE"])
        kontrol.pack(fill="x", pady=(6, 0))
        tk.Button(kontrol, text="−", command=lambda: self._zoom_degistir(-0.5),
                  bg=p["SURFACE"], fg=p["TEXT"], relief="flat", width=3,
                  cursor="hand2").pack(side="left", padx=2)
        tk.Button(kontrol, text="+", command=lambda: self._zoom_degistir(0.5),
                  bg=p["SURFACE"], fg=p["TEXT"], relief="flat", width=3,
                  cursor="hand2").pack(side="left", padx=2)
        self.sayfa_label = tk.Label(kontrol, text="", bg=p["MANTLE"],
                                    fg=p["SUBTEXT"], font=("Arial", 8))
        self.sayfa_label.pack(side="left", padx=8)
        tk.Button(kontrol, text="◀", command=lambda: self._sayfa_degistir(-1),
                  bg=p["SURFACE"], fg=p["TEXT"], relief="flat", width=3,
                  cursor="hand2").pack(side="left", padx=2)
        tk.Button(kontrol, text="▶", command=lambda: self._sayfa_degistir(1),
                  bg=p["SURFACE"], fg=p["TEXT"], relief="flat", width=3,
                  cursor="hand2").pack(side="left", padx=2)
        self.dis_ac_btn = tk.Button(kontrol, text="Dışarıda Aç",
                                    command=self._disarida_ac, bg=p["SURFACE"],
                                    fg=p["BLUE"], relief="flat", padx=8,
                                    cursor="hand2")
        self.dis_ac_btn.pack(side="right", padx=2)

    def _onizleme_yukle(self, yol):
        self._pdf_yol = yol
        self.sayfa = 0
        if self._pdf_doc is not None:
            self._pdf_doc.close()
            self._pdf_doc = None
        if not yol or not str(yol).lower().endswith(".pdf") or not os.path.exists(yol):
            self.onizleme_label.config(image="", text="Önizleme yok (XML / PDF bulunamadı)")
            self._tk_img = None
            self.sayfa_label.config(text="")
            self.dis_ac_btn.config(state="disabled")
            return
        try:
            self._pdf_doc = fitz.open(yol)
        except Exception:
            self.onizleme_label.config(image="", text="Önizleme yüklenemedi")
            self._tk_img = None
            self.sayfa_label.config(text="")
            self.dis_ac_btn.config(state="disabled")
            return
        self.dis_ac_btn.config(state="normal")
        self._sayfayi_ciz()

    def _sayfayi_ciz(self):
        if self._pdf_doc is None:
            return
        n = self._pdf_doc.page_count
        self.sayfa = max(0, min(self.sayfa, n - 1))
        try:
            pix = self._pdf_doc[self.sayfa].get_pixmap(
                matrix=fitz.Matrix(self.zoom, self.zoom))
            png_b64 = base64.b64encode(pix.tobytes("png")).decode()
            self._tk_img = tk.PhotoImage(data=png_b64)
            self.onizleme_label.config(image=self._tk_img, text="")
        except Exception:
            self.onizleme_label.config(image="", text="Önizleme yüklenemedi")
            self._tk_img = None
        self.sayfa_label.config(text=f"sayfa {self.sayfa + 1} / {n}")

    def _zoom_degistir(self, d):
        self.zoom = max(0.5, min(4.0, self.zoom + d))
        self._sayfayi_ciz()

    def _sayfa_degistir(self, d):
        if self._pdf_doc is None:
            return
        self.sayfa += d
        self._sayfayi_ciz()

    def _disarida_ac(self):
        if self._pdf_yol and os.path.exists(self._pdf_yol):
            os.startfile(self._pdf_yol)
```

- [ ] **Step 2: Write a preview smoke script (gerçek PDF ile)**

`_smoke_preview.py` (geçici):

```python
"""Gömülü önizleme smoke: fitz ile geçici PDF üret, ReviewWindow'da göster, ekran görüntüsü al."""
import os, tempfile, tkinter as tk
import fitz
from PIL import ImageGrab
from review_ui import ReviewWindow

PALET = {"BG": "#1e1e2e", "MANTLE": "#181825", "SURFACE": "#313244",
         "TEXT": "#cdd6f4", "SUBTEXT": "#a6adc8", "BLUE": "#89b4fa",
         "GREEN": "#a6e3a1", "RED": "#f38ba8", "OVERLAY": "#6c7086"}

pdf_yol = os.path.join(tempfile.gettempdir(), "smoke_fatura.pdf")
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), "ORNEK FATURA\nGIB2024000000123\nTutar: 1.180,00 TL")
doc.save(pdf_yol); doc.close()

payload = {"mevcut": [], "yeni": [
    {"fatura_no": "GIB2024000000123", "sirket_adi": "ACME",
     "vergiler_dahil_tutar": 1180.0, "_teknik_bilgi": "Dijital",
     "dosya_yolu": pdf_yol}],
    "atlanmis": [], "uyarilar": [], "cikti": "x.xlsx", "kesildi": False}

root = tk.Tk(); root.withdraw()
rw = ReviewWindow(root, payload, PALET, lambda n, u: True, lambda: None)
rw.win.lift(); rw.win.attributes("-topmost", True)
root.update_idletasks(); root.update()
x, y = rw.win.winfo_rootx(), rw.win.winfo_rooty()
w, h = rw.win.winfo_width(), rw.win.winfo_height()
out = os.path.join(os.environ.get("TEMP", "."), "preview_smoke.png")
ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out)
print("OK ->", out)
root.destroy()
```

- [ ] **Step 3: Run preview smoke and view screenshot**

Run: `python _smoke_preview.py`
Expected: `OK -> ...preview_smoke.png`. Ekran görüntüsünde sağ panelde PDF'in ilk sayfasının render edildiğini, "sayfa 1 / 1" ve zoom/dışarıda-aç butonlarını gör. Sonra `rm _smoke_preview.py`.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add review_ui.py
git commit -m "feat: ReviewWindow gömülü PDF önizleme (zoom, sayfa, dışarıda aç)"
```

---

## Task 7: gui.py — "review" olayını bağla

**Files:**
- Modify: `gui.py`

- [ ] **Step 1: Add imports**

`gui.py` içindeki `from worker import worker` satırından sonra ekle:

```python
from review_ui import ReviewWindow
from excel_utils import excel_olustur, ExcelHatasi
```

- [ ] **Step 2: Replace the "done" handler in _poll_queue**

`gui.py` `_poll_queue` içindeki şu bloğu:

```python
                elif tag == "done":
                    atlanmis, islenen, uyarilar = data
                    self._atlanmis = atlanmis
                    self._uyarilar = uyarilar
                    self._gecmis_kaydet(islenen, len(atlanmis))
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.btn_tema.config(state="normal")
                    if self.son_cikti and os.path.exists(self.son_cikti):
                        self.btn_excel.config(state="normal")
                    if atlanmis:
                        self.btn_retry.config(state="normal",
                            text=f"↺ Yeniden Dene ({len(atlanmis)})")
                    if uyarilar:
                        toplam_u = sum(len(u) for _, u in uyarilar)
                        self.btn_uyari.config(state="normal",
                            text=f"⚠ Uyarılar ({toplam_u})")
                    else:
                        self.btn_uyari.config(state="disabled", text="⚠ Uyarılar")
```

şununla değiştir:

```python
                elif tag == "done":
                    atlanmis, islenen, uyarilar = data
                    self._islem_bitti(atlanmis, islenen, uyarilar)

                elif tag == "review":
                    self._review_ac(data)
```

- [ ] **Step 3: Add the helper methods**

`_poll_queue` metodundan hemen sonra (Log yardımcıları bölümünden önce) şu metotları ekle:

```python
    # ── İşlem sonu ve onay penceresi ───────────────────────────────────
    def _islem_bitti(self, atlanmis, islenen, uyarilar):
        self._atlanmis = atlanmis
        self._uyarilar = uyarilar
        self._gecmis_kaydet(islenen, len(atlanmis))
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_tema.config(state="normal")
        if self.son_cikti and os.path.exists(self.son_cikti):
            self.btn_excel.config(state="normal")
        if atlanmis:
            self.btn_retry.config(state="normal",
                                  text=f"↺ Yeniden Dene ({len(atlanmis)})")
        if uyarilar:
            toplam_u = sum(len(u) for _, u in uyarilar)
            self.btn_uyari.config(state="normal", text=f"⚠ Uyarılar ({toplam_u})")
        else:
            self.btn_uyari.config(state="disabled", text="⚠ Uyarılar")

    def _review_ac(self, payload):
        self._review_payload = payload
        palet = {"BG": BG, "MANTLE": MANTLE, "SURFACE": SURFACE, "TEXT": TEXT,
                 "SUBTEXT": SUBTEXT, "BLUE": BLUE, "GREEN": GREEN, "RED": RED,
                 "OVERLAY": OVERLAY}
        ReviewWindow(self.root, payload, palet,
                     self._review_onayla, self._review_iptal)

    def _review_onayla(self, nihai, guncel_uyarilar):
        payload = self._review_payload
        try:
            excel_olustur(nihai, payload["cikti"])
        except ExcelHatasi as e:
            messagebox.showerror("Excel kaydedilemedi", str(e))
            return False
        self.son_cikti = payload["cikti"]
        yazilan = len(nihai) - len(payload["mevcut"])
        self._log("done_ok",
                  f"Excel oluşturuldu: {payload['cikti']}  "
                  f"({len(nihai)} fatura, {yazilan} yeni)")
        self._islem_bitti(payload["atlanmis"], yazilan, guncel_uyarilar)
        return True

    def _review_iptal(self):
        payload = self._review_payload
        self._log("info", "İşlem iptal edildi, hiçbir şey kaydedilmedi.")
        self._islem_bitti(payload["atlanmis"], 0, [])
```

- [ ] **Step 4: Verify gui.py parses and imports**

Run: `python -c "import ast; ast.parse(open('gui.py',encoding='utf-8').read()); print('syntax OK')"`
Run: `python -c "import gui; print('import OK')"`
Expected: her ikisi de OK (hata yok).

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add gui.py
git commit -m "feat: gui review penceresini açar, onayda Excel yazar"
```

---

## Task 8: Uçtan uca entegrasyon doğrulaması + dokümantasyon

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: End-to-end smoke (worker → review payload → write)**

`_smoke_e2e.py` (geçici):

```python
"""Worker review payload üretir; nihai_satirlar + excel_olustur ile yazım doğrulanır."""
import os, queue, shutil, tempfile, threading
import google.genai
from review import nihai_satirlar
from excel_utils import excel_olustur, mevcut_verileri_oku

# genai.Client'ı sahtele (XML için kullanılmaz)
google.genai.Client = lambda **kw: object()

from worker import worker

klasor = tempfile.mkdtemp()
shutil.copy("tests/fixtures/ornek_fatura.xml", os.path.join(klasor, "f.xml"))
log_q = queue.Queue(); worker("KEY", klasor, "cikti.xlsx", log_q, threading.Event())

payload = None
while not log_q.empty():
    t, d = log_q.get_nowait()
    if t == "review":
        payload = d
assert payload and len(payload["yeni"]) == 1, "review payload bekleniyordu"
assert not os.path.exists(os.path.join(klasor, "cikti.xlsx")), "worker yazmamali"

nihai = nihai_satirlar(payload["mevcut"], payload["yeni"], set())
excel_olustur(nihai, payload["cikti"])
okunan, _ = mevcut_verileri_oku(payload["cikti"])
assert len(okunan) == 1, "Excel'de 1 satır olmalı"
print("E2E OK:", payload["cikti"])
```

- [ ] **Step 2: Run the e2e smoke**

Run: `python _smoke_e2e.py`
Expected: `E2E OK: ...cikti.xlsx` (assert hatası yok). Sonra `rm _smoke_e2e.py`.

- [ ] **Step 3: Manual GUI verification**

Run: `python main.py`
Adımlar: PDF/XML içeren bir klasör seç → Başlat → işlem bitince **Gözden Geçir penceresi açılmalı**. Doğrula:
- Uyarılı satır sarı, ilk uyarılı satır otomatik seçili.
- Bir alanı değiştir → "Uygula" → tablo ve uyarı güncellenir.
- Sağda PDF önizleme görünür; zoom/sayfa/Dışarıda Aç çalışır (PDF'lerde).
- "Bu faturayı hariç tut" → satır grileşir.
- "Onayla & Excel" → Excel yazılır, ana ekranda "Excel'i Aç" aktifleşir.
- Tekrar dene: "İptal" → onay sorar, hiçbir şey yazılmaz.

- [ ] **Step 4: Update CLAUDE.md**

`CLAUDE.md` "Module Responsibilities" bölümünde `worker.py` maddesinden sonra ekle:

```markdown
- **`review.py`** – Onay/düzeltme arayüzünün saf mantığı (tkinter yok): `DUZENLENEBILIR_ALANLAR`, `satir_form_degerleri`, `form_satira_uygula` (form metnini `to_float`/`tarih_parse` ile tipli değere çevirir), `nihai_satirlar`.
- **`review_ui.py`** – `ReviewWindow` (Toplevel): Excel yazılmadan önce yeni faturaların master-detail gözden geçirme/düzeltme penceresi. Gömülü PDF önizleme (`fitz` → base64 PNG → `tk.PhotoImage`), satır hariç tutma, uyarıya hızlı atlama. Renk paleti parametreyle alınır (dairesel import'tan kaçınmak için).
```

`CLAUDE.md` "Data Flow" bölümünde 7. maddeyi şununla değiştir:

```markdown
7. İşlem bitince worker `("review", payload)` yayınlar; GUI `ReviewWindow` açar. Kullanıcı düzeltir/hariç tutar/onaylar; **Excel ancak onaydan sonra** `excel_olustur` ile yazılır. İptal'de hiçbir şey yazılmaz.
```

- [ ] **Step 5: Commit + merge**

```bash
git add CLAUDE.md
git commit -m "docs: review.py/review_ui.py ve onay akışı CLAUDE.md'ye eklendi"
git checkout master
git merge --no-ff onay-duzeltme-arayuzu -m "merge: Onay/düzeltme arayüzü"
```

---

## Self-Review Notları

- **Spec kapsamı:** Zamanlama (bitince/tüm yeni) → Task 4 `_bitir`; master-detail + form → Task 5; gömülü önizleme + dışarıda aç → Task 6; hariç tut/anlık uyarı/atlama → Task 5; tüm 11 alan → Task 1 `DUZENLENEBILIR_ALANLAR`; Excel ertelemesi → Task 4/7; hata yönetimi (dosya kilitli → pencere açık) → Task 7 `_review_onayla` False dönüşü; testler → Task 1-4 + smoke'lar.
- **Tip tutarlılığı:** `on_confirm(nihai, guncel_uyarilar) -> bool` (review_ui Task 5 ↔ gui Task 7); payload anahtarları `mevcut/yeni/atlanmis/uyarilar/cikti/kesildi` (worker Task 4 ↔ review_ui Task 5 ↔ gui Task 7) tutarlı.
- **Placeholder yok:** Tüm kod blokları eksiksiz.
