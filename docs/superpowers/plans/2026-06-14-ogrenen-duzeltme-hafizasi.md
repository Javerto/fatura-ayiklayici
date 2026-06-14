# Öğrenen Düzeltme Hafızası — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review penceresinde firma-sabit alanları (`sirket_adi`, `vergi_dairesi`) düzeltip "hatırla" işaretleyince, VKN bazlı kural kaydedip sonraki çalıştırmalarda aynı firmanın faturalarına otomatik uygulamak.

**Architecture:** Yeni saf-mantık modülü `duzeltme.py` kuralları JSON'da tutar (oku/yaz/uygula/ekle). Worker, çıkarılan her satıra `kural_uygula`'yı `veri_dogrula`'dan önce uygular. Review penceresi "hatırla" checkbox'ıyla `{vkn: {alanlar}}` toplar ve onayda dışarı verir; gui bunu `duzeltmeler.json`'a (AppData-duyarlı) yazar. AI prompt'una dokunulmaz.

**Tech Stack:** Python 3.13, json (stdlib), tkinter (review_ui/gui), pytest.

**Not (Python yolu):** Bu ortamda `python` PATH'te değil. Komutlarda tam yol kullan:
`PY="/c/Users/PC/AppData/Local/Programs/Python/Python313/python.exe"`

---

### Task 1: `duzeltme.py` — saf kural mantığı

**Files:**
- Create: `duzeltme.py`
- Test: `tests/test_duzeltme.py`

- [ ] **Step 1: Testleri yaz**

`tests/test_duzeltme.py`:

```python
"""duzeltme.py — öğrenen düzeltme kuralları saf mantık testleri."""
from duzeltme import (OGRENILEN_ALANLAR, kurallari_oku, kurallari_yaz,
                      kural_uygula, kural_ekle)


def test_ogrenilen_alanlar_para_birimi_iceremez():
    assert set(OGRENILEN_ALANLAR) == {"sirket_adi", "vergi_dairesi"}


def test_kurallari_oku_dosya_yoksa_bos_doner(tmp_path):
    assert kurallari_oku(tmp_path / "yok.json") == {}


def test_kurallari_oku_bozuk_json_bos_doner(tmp_path):
    yol = tmp_path / "bozuk.json"
    yol.write_text("{ bu gecersiz", encoding="utf-8")
    assert kurallari_oku(yol) == {}


def test_kurallari_yaz_ve_oku_roundtrip(tmp_path):
    yol = tmp_path / "k.json"
    veri = {"1234567890": {"sirket_adi": "ACME A.Ş."}}
    kurallari_yaz(yol, veri)
    assert kurallari_oku(yol) == veri


def test_kural_uygula_eslesirse_alanlari_ezer():
    kurallar = {"1234567890": {"sirket_adi": "ARÇELİK A.Ş.",
                               "vergi_dairesi": "Büyük Mükellefler"}}
    satir = {"vkn": "1234567890", "sirket_adi": "ARCELIK AS",
             "vergi_dairesi": "", "fatura_no": "X"}
    sonuc = kural_uygula(satir, kurallar)
    assert sonuc["sirket_adi"] == "ARÇELİK A.Ş."
    assert sonuc["vergi_dairesi"] == "Büyük Mükellefler"
    assert sonuc["fatura_no"] == "X"        # öğrenilmeyen alan korunur


def test_kural_uygula_eslesmezse_degismez():
    kurallar = {"1111111111": {"sirket_adi": "X"}}
    satir = {"vkn": "9999999999", "sirket_adi": "ORİJİNAL"}
    assert kural_uygula(satir, kurallar)["sirket_adi"] == "ORİJİNAL"


def test_kural_uygula_vkn_yoksa_degismez():
    kurallar = {"1234567890": {"sirket_adi": "X"}}
    satir = {"sirket_adi": "ORİJİNAL"}
    assert kural_uygula(satir, kurallar)["sirket_adi"] == "ORİJİNAL"


def test_kural_uygula_orijinali_bozmaz():
    kurallar = {"1234567890": {"sirket_adi": "YENİ"}}
    satir = {"vkn": "1234567890", "sirket_adi": "ESKİ"}
    kural_uygula(satir, kurallar)
    assert satir["sirket_adi"] == "ESKİ"     # kopya döner, mutasyon yok


def test_kural_ekle_yeni_vkn_ekler():
    sonuc = kural_ekle({}, "1234567890",
                       {"sirket_adi": "ACME", "vergi_dairesi": "Kadıköy"})
    assert sonuc == {"1234567890": {"sirket_adi": "ACME",
                                    "vergi_dairesi": "Kadıköy"}}


def test_kural_ekle_bos_degerleri_atlar():
    sonuc = kural_ekle({}, "1234567890",
                       {"sirket_adi": "ACME", "vergi_dairesi": "   "})
    assert sonuc == {"1234567890": {"sirket_adi": "ACME"}}


def test_kural_ekle_tum_degerler_bossa_kural_olusmaz():
    assert kural_ekle({}, "1234567890",
                      {"sirket_adi": "", "vergi_dairesi": None}) == {}


def test_kural_ekle_vkn_bossa_degismez():
    assert kural_ekle({"a": {"sirket_adi": "X"}}, "", {"sirket_adi": "Y"}) == \
        {"a": {"sirket_adi": "X"}}


def test_kural_ekle_orijinali_bozmaz():
    kurallar = {"1234567890": {"sirket_adi": "ESKİ"}}
    kural_ekle(kurallar, "1234567890", {"sirket_adi": "YENİ"})
    assert kurallar["1234567890"]["sirket_adi"] == "ESKİ"
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `"$PY" -m pytest tests/test_duzeltme.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'duzeltme'`

- [ ] **Step 3: `duzeltme.py`'yi yaz**

`duzeltme.py`:

```python
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
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `"$PY" -m pytest tests/test_duzeltme.py -q`
Expected: PASS (13 test)

- [ ] **Step 5: Commit**

```bash
git add duzeltme.py tests/test_duzeltme.py
git commit -m "feat: duzeltme.py — VKN bazli ogrenen duzeltme kurallari (saf mantik)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `worker.py` — kuralları çıkarma sonrası uygula

**Files:**
- Modify: `worker.py` (import, `worker(...)` imzası, `islendi` başı)
- Test: `tests/test_worker.py` (yeni test ekle)

- [ ] **Step 1: Yeni testi yaz**

`tests/test_worker.py` dosyasının sonuna ekle:

```python
def test_worker_kurallari_uygular(tmp_path):
    """vkn eşleşen kural, review payload'undaki satıra uygulanır."""
    shutil.copy(FIXTURE, tmp_path / "fatura1.xml")
    log_q = queue.Queue()
    stop = threading.Event()
    kurallar = {"1234567890": {"sirket_adi": "DÜZELTİLMİŞ A.Ş."}}

    worker("FAKE_KEY", str(tmp_path), "cikti.xlsx", log_q, stop,
           kurallar=kurallar)

    mesajlar = _kuyrugu_bosalt(log_q)
    payload = next(d for t, d in mesajlar if t == "review")
    assert payload["yeni"][0]["sirket_adi"] == "DÜZELTİLMİŞ A.Ş."
```

(Not: `tests/fixtures/ornek_fatura.xml` satıcı VKN'si `1234567890`'dır.)

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `"$PY" -m pytest tests/test_worker.py::test_worker_kurallari_uygular -q`
Expected: FAIL — `TypeError: worker() got an unexpected keyword argument 'kurallar'`

- [ ] **Step 3: `worker.py`'yi düzenle**

3a. Import bloğuna (`from excel_utils import mevcut_verileri_oku` satırının altına) ekle:

```python
from duzeltme import kural_uygula
```

3b. `worker(...)` imzasını şu şekilde değiştir (mevcut imza `zoom: float = 1.5` ile bitiyor):

```python
def worker(api_key: str, klasor: str, cikti_adi: str, log_q: queue.Queue,
           stop_event: threading.Event, retry_dosyalar: list | None = None,
           zoom: float = 1.5, kurallar: dict | None = None):
```

3c. `def log(tag, mesaj):` bloğunun hemen altına (try'dan önce) ekle:

```python
    kurallar = kurallar or {}
```

3d. `def islendi(veri):` fonksiyonunun ilk satırı `nonlocal siradaki`'den hemen sonra ekle:

```python
        veri = kural_uygula(veri, kurallar)
```

- [ ] **Step 4: Tüm worker testlerinin geçtiğini doğrula**

Run: `"$PY" -m pytest tests/test_worker.py -q`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add worker.py tests/test_worker.py
git commit -m "feat: worker cikarilan satira ogrenen duzeltme kurallarini uygular

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `review.py` — `ogrenilecek_alanlar` yardımcısı

**Files:**
- Modify: `review.py` (import + yeni fonksiyon)
- Test: `tests/test_review.py` (yeni testler ekle)

- [ ] **Step 1: Testleri yaz**

`tests/test_review.py` dosyasının import satırlarına `ogrenilecek_alanlar`'ı ekle ve sona testleri koy.

İmport satırını şununla değiştir:

```python
from review import (DUZENLENEBILIR_ALANLAR, satir_form_degerleri,
                    form_satira_uygula, nihai_satirlar, ogrenilecek_alanlar)
```

Dosyanın sonuna ekle:

```python
def test_ogrenilecek_alanlar_sadece_firma_sabit_dolu():
    row = {"sirket_adi": "ACME A.Ş.", "vergi_dairesi": "Kadıköy",
           "fatura_no": "X", "para_birimi": "TL", "vkn": "1234567890"}
    assert ogrenilecek_alanlar(row) == {"sirket_adi": "ACME A.Ş.",
                                        "vergi_dairesi": "Kadıköy"}


def test_ogrenilecek_alanlar_bos_atlanir():
    assert ogrenilecek_alanlar({"sirket_adi": "  ",
                                "vergi_dairesi": "Ankara"}) == \
        {"vergi_dairesi": "Ankara"}
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `"$PY" -m pytest tests/test_review.py -q`
Expected: FAIL — `ImportError: cannot import name 'ogrenilecek_alanlar'`

- [ ] **Step 3: `review.py`'yi düzenle**

3a. İmport satırına ekle (mevcut: `from extraction import to_float, tarih_parse`):

```python
from duzeltme import OGRENILEN_ALANLAR
```

3b. Dosyanın sonuna fonksiyonu ekle:

```python
def ogrenilecek_alanlar(row: dict) -> dict:
    """Satırdan öğrenilebilir (firma-sabit) alanların dolu olanlarını döndürür."""
    sonuc = {}
    for alan in OGRENILEN_ALANLAR:
        deger = row.get(alan)
        if isinstance(deger, str):
            deger = deger.strip()
        if deger:
            sonuc[alan] = deger
    return sonuc
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `"$PY" -m pytest tests/test_review.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add review.py tests/test_review.py
git commit -m "feat: review.ogrenilecek_alanlar — satirdan firma-sabit alanlari ayikla

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `review_ui.py` — "hatırla" checkbox'ı ve kural toplama

**Files:**
- Modify: `review_ui.py` (import, `__init__`, form, `_satir_secildi`, `_uygula`, `_onayla`, docstring)

Not: tkinter UI olduğu için birim test yok; görsel test Task 6'da. Toplama mantığının saf çekirdeği Task 3'te test edildi.

- [ ] **Step 1: İmport satırını genişlet**

`review_ui.py` içindeki import'u şununla değiştir:

```python
from review import (DUZENLENEBILIR_ALANLAR, satir_form_degerleri,
                    form_satira_uygula, nihai_satirlar, ogrenilecek_alanlar)
```

- [ ] **Step 2: docstring'i ve `__init__`'i güncelle**

2a. Sınıf docstring'indeki `on_confirm` satırını şununla değiştir:

```python
    on_confirm(nihai_satirlar, guncel_uyarilar, yeni_kurallar) -> bool
        True dönerse pencere kapanır (yazım başarılı), False ise açık kalır.
        yeni_kurallar: {vkn: {alan: deger}} — "hatırla" ile toplanan kurallar.
```

2b. `__init__` içinde `self.form_vars = {}` satırının altına ekle:

```python
        self.toplanan_kurallar = {}
```

- [ ] **Step 3: Forma "hatırla" checkbox'ı ekle**

`_build` içinde, form_frame'deki `uyari_label` ile "Uygula" butonu arasına checkbox ekle ve Uygula'yı bir satır aşağı kaydır.

Mevcut "Uygula" buton bloğunu:

```python
        tk.Button(form_frame, text="Uygula", command=self._uygula,
                  bg=p["SURFACE"], fg=p["GREEN"], relief="flat", padx=12,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["GREEN"]
                  ).grid(row=len(DUZENLENEBILIR_ALANLAR) + 1, column=0,
                         columnspan=2, pady=6)
```

şununla değiştir:

```python
        self.hatirla_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            form_frame, text="Bu düzeltmeleri firma için hatırla (VKN)",
            variable=self.hatirla_var, bg=p["MANTLE"], fg=p["TEXT"],
            selectcolor=p["SURFACE"], activebackground=p["MANTLE"],
            font=("Arial", 8)).grid(row=len(DUZENLENEBILIR_ALANLAR) + 1,
                                    column=0, columnspan=2, sticky="w", padx=4)
        tk.Button(form_frame, text="Uygula", command=self._uygula,
                  bg=p["SURFACE"], fg=p["GREEN"], relief="flat", padx=12,
                  cursor="hand2", activebackground=p["SURFACE"],
                  activeforeground=p["GREEN"]
                  ).grid(row=len(DUZENLENEBILIR_ALANLAR) + 2, column=0,
                         columnspan=2, pady=6)
```

- [ ] **Step 4: Seçim değişince checkbox'ı sıfırla**

`_satir_secildi` içinde `self.haric_var.set(i in self.haric)` satırının altına ekle:

```python
        self.hatirla_var.set(False)
```

- [ ] **Step 5: `_uygula`'da kuralı topla**

Mevcut `_uygula` metodunu şununla değiştir:

```python
    def _uygula(self):
        if self.secili is None:
            return
        i = self.secili
        form = {a: v.get() for a, v in self.form_vars.items()}
        self.yeni[i] = form_satira_uygula(self.yeni[i], form)
        self.uyari[i] = veri_dogrula(self.yeni[i])
        self._uyari_goster(i)
        self._tabloyu_guncelle(i)
        if self.hatirla_var.get():
            vkn = str(self.yeni[i].get("vkn") or "").strip()
            alanlar = ogrenilecek_alanlar(self.yeni[i])
            if vkn and alanlar:
                self.toplanan_kurallar[vkn] = alanlar
                messagebox.showinfo(
                    "Kaydedilecek",
                    "Düzeltme bu firma için hatırlanacak.", parent=self.win)
            else:
                messagebox.showwarning(
                    "Kaydedilemedi",
                    "Kural kaydı için geçerli bir VKN ve firma bilgisi gerekli.",
                    parent=self.win)
            self.hatirla_var.set(False)
```

- [ ] **Step 6: `_onayla`'da kuralları dışarı ver**

`_onayla` içindeki `if self.on_confirm(nihai, guncel_uyarilar):` satırını şununla değiştir:

```python
        if self.on_confirm(nihai, guncel_uyarilar, self.toplanan_kurallar):
```

- [ ] **Step 7: Mevcut testlerin hâlâ geçtiğini doğrula (regression)**

Run: `"$PY" -m pytest -q`
Expected: PASS (review_ui import edilebiliyor; tüm mevcut testler yeşil)

- [ ] **Step 8: Commit**

```bash
git add review_ui.py
git commit -m "feat: review penceresine 'firma icin hatirla' checkbox'i + kural toplama

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `gui.py` — kuralları yükle (worker'a geçir) ve onayda kaydet

**Files:**
- Modify: `gui.py` (import, yol sabiti, `_basla`, `_yeniden_dene`, `_review_onayla`, yeni `_kurallari_kaydet`)

- [ ] **Step 1: İmport ve yol sabiti ekle**

1a. `from excel_utils import excel_olustur, ExcelHatasi` satırının altına ekle:

```python
from duzeltme import kurallari_oku, kurallari_yaz, kural_ekle
```

1b. `GECMIS_DOSYASI = _BASE / "gecmis.json"` satırının altına ekle:

```python
DUZELTME_DOSYASI = _BASE / "duzeltmeler.json"
```

- [ ] **Step 2: `_basla`'da kuralları worker'a geçir**

`_basla` içindeki worker thread'inin `kwargs`'ını şununla değiştir:

```python
            kwargs={"zoom": float(self.zoom_var.get()),
                    "kurallar": kurallari_oku(DUZELTME_DOSYASI)},
```

- [ ] **Step 3: `_yeniden_dene`'de kuralları worker'a geçir**

`_yeniden_dene` içindeki worker thread'inin `kwargs`'ını şununla değiştir:

```python
            kwargs={"retry_dosyalar": retry_yollar,
                    "zoom": float(self.zoom_var.get()),
                    "kurallar": kurallari_oku(DUZELTME_DOSYASI)},
```

- [ ] **Step 4: `_review_onayla` imzasını genişlet ve kuralları kaydet**

`_review_onayla` metodunu şununla değiştir (yalnızca imza + başa kayıt eklenir, gerisi aynı):

```python
    def _review_onayla(self, nihai, guncel_uyarilar, yeni_kurallar):
        if yeni_kurallar:
            self._kurallari_kaydet(yeni_kurallar)
        payload = self._review_payload
        if len(nihai) == len(payload["mevcut"]):
            # Tüm yeni faturalar hariç tutuldu — Excel'e dokunma (spec)
            self._log("info", "Tüm yeni faturalar hariç tutuldu, Excel'e dokunulmadı.")
            self._islem_bitti(payload["atlanmis"], 0, guncel_uyarilar)
            return True
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
```

- [ ] **Step 5: `_kurallari_kaydet` metodunu ekle**

`_review_iptal` metodunun hemen üstüne ekle:

```python
    def _kurallari_kaydet(self, yeni_kurallar):
        kurallar = kurallari_oku(DUZELTME_DOSYASI)
        for vkn, alanlar in yeni_kurallar.items():
            kurallar = kural_ekle(kurallar, vkn, alanlar)
        try:
            kurallari_yaz(DUZELTME_DOSYASI, kurallar)
            self._log("info",
                      f"{len(yeni_kurallar)} firma için düzeltme kuralı kaydedildi.")
        except OSError as e:
            self._log("warn", f"Düzeltme kuralları kaydedilemedi: {e}")
```

- [ ] **Step 6: İçe aktarma/söz dizimi doğrulaması**

Run: `"$PY" -c "import gui"`
Expected: Hata yok (çıktı boş)

- [ ] **Step 7: Commit**

```bash
git add gui.py
git commit -m "feat: gui duzeltme kurallarini worker'a gecirir ve onayda kaydeder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Doğrulama — tüm testler, görsel test, dokümantasyon

**Files:**
- Modify: `CLAUDE.md` (yeni modül + akış notu)

- [ ] **Step 1: Tüm test paketini çalıştır**

Run: `"$PY" -m pytest -q`
Expected: PASS (mevcut 92 + yeni ~15 test, kırmızı yok)

- [ ] **Step 2: Görsel test (gerçek GUI)**

Run: `"$PY" main.py`
Kontrol et:
1. Bir klasördeki faturaları işle → review penceresi açılır.
2. Bir faturada `sirket_adi`'ni düzelt, "Bu düzeltmeleri firma için hatırla (VKN)" kutusunu işaretle, **Uygula** → "Kaydedilecek" bilgi kutusu çıkar.
3. VKN'si boş bir faturada kutuyu işaretleyip Uygula → "Kaydedilemedi" uyarısı çıkar.
4. **Onayla & Excel** → proje klasöründe (veya AppData, EXE modunda) `duzeltmeler.json` oluşur; içinde `{"<vkn>": {"sirket_adi": "..."}}` vardır.
5. Aynı VKN'li faturayı yeniden işle (Excel'i/çıkış adını değiştirerek) → review'da `sirket_adi` otomatik düzeltilmiş gelir.

- [ ] **Step 3: `CLAUDE.md`'yi güncelle**

`### Module Responsibilities` altına, `ozet.py` maddesinin altına ekle:

```markdown
- **`duzeltme.py`** – Öğrenen düzeltme kuralları (saf mantık, tkinter/Excel'siz). VKN bazlı firma-sabit alan kuralları (`OGRENILEN_ALANLAR = ["sirket_adi", "vergi_dairesi"]`) için `kurallari_oku`/`kurallari_yaz`/`kural_uygula`/`kural_ekle`. Kurallar `duzeltmeler.json`'da tutulur (frozen modda AppData). `para_birimi` bilinçli olarak kapsam dışı (faturaya özel). Worker, çıkarılan her satıra `kural_uygula`'yı `veri_dogrula`'dan önce uygular; review'da "hatırla" checkbox'ı kuralları toplar, gui onayda kaydeder.
```

`### Configuration and State` altına ekle:

```markdown
- **`duzeltmeler.json`** – VKN bazlı öğrenen düzeltme kuralları. Frozen modda `%APPDATA%\FaturaAyiklayici`, değilse proje klasöründe.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: duzeltme.py modulu ve ogrenen duzeltme akisi CLAUDE.md'ye eklendi

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notları

- **Spec kapsamı:** `duzeltme.py` (Task 1) ✓, worker entegrasyonu (Task 2) ✓, review checkbox + toplama (Task 3+4) ✓, gui yükle/kaydet + AppData yol (Task 5) ✓, testler (Task 1-3) + görsel test (Task 6) ✓, `para_birimi` kapsam dışı (OGRENILEN_ALANLAR) ✓.
- **Sınır durumları:** VKN yok/eşleşmez → `kural_uygula` değiştirmez (test ✓). Bozuk JSON → `{}` (test ✓). VKN boşken "hatırla" → uyarı, kayıt yok (review_ui Step 5). İptal → kural kaydedilmez (`_review_iptal` değişmedi).
- **Tip tutarlılığı:** `on_confirm(nihai, guncel_uyarilar, yeni_kurallar)` — review_ui `_onayla` ve gui `_review_onayla` aynı 3 argüman. `worker(..., kurallar=None)` — gui her iki çağrıda kwargs ile, test pozitif. `kurallar`/`kural`/`alanlar` adları tüm modüllerde tutarlı.
