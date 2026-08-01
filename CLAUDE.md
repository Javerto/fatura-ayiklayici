# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Dil Kuralı
- ALWAYS respond in Turkish (Türkçe).
- Tüm açıklamalar, commit mesajları ve yorumlar Türkçe olmalı.
- Kod içindeki değişken/fonksiyon isimleri İngilizce kalabilir ama kullanıcıyla iletişim her zaman Türkçe olmalı.

## Overview

Fatura Ayıklayıcı is a Turkish-language desktop application for extracting invoice data from PDF/XML e-invoices using Google's Gemini AI. The UI is HTML/CSS/JS rendered in a **pywebview** window (Windows WebView2); Python holds all logic. Designed for non‑technical users. It outputs a formatted Excel file with hyperlinks to source documents.

Key characteristics:
- **Target users**: Non‑technical colleagues; zero‑install EXE distribution
- **Language**: Turkish UI, logs, error messages, and commit messages
- **Platform**: Windows (EXE built with PyInstaller)
- **AI model**: Google Gemini (Gemma‑4‑31b‑it) via `google‑genai`
- **File formats**: PDF (hybrid: digital text first, OCR/image fallback), XML (UBL e‑invoice parsing)
- **Output**: Excel with validation, warnings, and clickable file links

## Development Commands

### Dependencies
```bash
pip install -r requirements.txt
# veya tek tek:
pip install google-genai pymupdf python-dotenv openpyxl pywebview
```

### Run the GUI
```bash
python main.py
```

### Build the EXE
```bash
build.bat
```
The batch script creates a clean virtual environment, installs dependencies, builds an icon, and runs PyInstaller with the following flags:
- `--onefile`, `--windowed`
- `--name "FaturaAyiklayici"`
- `--collect-all google.genai`, `--collect-all webview`
- `--add-data "web;web"` — **the `web/` folder must ship or the UI cannot load**
- Hidden imports: `fitz`, `openpyxl`, `dotenv`, `clr_loader`

The resulting EXE is placed in `dist/FaturaAyiklayici.exe` (~44 MB). Configuration files (`.env`, `gecmis.json`) are stored in `%APPDATA%\FaturaAyiklayici` when running as EXE, otherwise in the project folder.

### Testing
A pytest suite lives in `tests/` (config in `pytest.ini`, `pythonpath = .`). Run it with:
```bash
python -m pytest          # tüm testler
python -m pytest tests/test_xml.py -q   # tek dosya
python -m pytest -k fatura_no           # isim filtresiyle
```
164 tests. Coverage focuses on the pure, UI‑free logic: `_duzelt_fatura_no`, `_json_ayikla`, `to_float`, `tarih_parse`, `veri_dogrula`, the Excel URL/round‑trip helpers, `xml_den_veri_cek` (via `tests/fixtures/ornek_fatura.xml`), the Excel "Kaynak" column, and end‑to‑end `worker` runs for **both** the XML and the PDF path — the PDF path became testable once the model call moved behind the `gemini` seam (`worker(..., istemci=<sahte>)`, no network, no `google.genai` patching). `tests/test_gemini.py` pins the resilience contract: backoff ladder, `retry in Ns` override, API‑key errors never retried (against Google's real error text), unknown errors re‑raised raw, cancellation mid‑sleep, and the RPM limiter. Time is injected (`uyu`/`saat`) — with the real clock the ladder alone would take 225 seconds. It also covers `Api` (only callable public attributes — see below), `pencere_boyutu`, `review_onayla` (`tests/test_review_onayla.py` — the only path that writes Excel), and the **Python↔JS event contract** (`tests/test_olay_sozlesmesi.py`). `Api(kok=<path>)` takes the config directory per instance, so tests never touch the real `.env` / `gecmis.json` / `duzeltmeler.json`. `pytest.ini` filters third‑party `DeprecationWarning`s so output stays clean.

**Headless tests cannot catch UI‑layer bugs.** Three real defects during the pywebview migration were invisible to pytest: the startup hang (needed a real `Window` object), the dead‑UI race, and zoom looking broken (CSS shrank a correctly‑enlarged PNG). Always launch the app and have the user look. `py-spy dump --pid <pid>` is the tool for a frozen window. When testing code that does intra‑module imports, patch where the name is used (e.g. `worker.pdf_text_ayikla`), not where it is defined.

## Architecture

### Module Responsibilities
- **`main.py`** – Entry point; reads the saved window size, creates the pywebview window (`js_api=Api()`), wires `closing` to persist the size, and calls `webview.start()`. If start fails it shows a Turkish MessageBox explaining that WebView2 is missing.
- **`api.py`** – The JS ↔ Python bridge; replaced `gui.py`. Every **public** method is exposed to the UI as `pywebview.api.<name>()`. Handles folder selection, start/stop, settings (`.env`), history, the review screen (`satir_dogrula`, `review_onayla`, `review_iptal`, `onizleme`, `dosya_ac`) and `_pompa`, which drains `log_q` and pushes **batched** events to `window.olaylar([...])` — batching matters because 5 parallel PDFs emit dozens of events a second.
  - ⚠ **All internal state must be `_`‑prefixed.** pywebview recurses into every public attribute of the api object (`webview/util.py::get_functions`) to build the JS proxy; a public `Window` reference makes it walk `pencere.native.AccessibilityObject.Bounds.Empty…` forever and the app hangs on startup. `tests/test_api.py` guards this.
- **`web/`** – The whole UI, shipped inside the EXE via `--add-data "web;web"`.
  - `index.html` – main screen + review screen (hidden until needed; one window, no popups)
  - `app.js` – main screen, event handling, modals (`onayModal`/`bilgiModal` — never the browser's `confirm`/`alert`, which render as “127.0.0.1:… diyor ki” in WebView2)
  - `review.js` – review screen; row text lives here, typed values stay in Python
  - `style.css` – layout; `tema.css` – the six themes; `tema.js` – theme picker
- **`worker.py`** – The background processing loop (`worker(...)`). UI‑independent pure logic: scans the folder, runs PDF tasks in a `ThreadPoolExecutor`, processes XML‑only files sequentially, and reports progress through the `log_q` queue and `stop_event`. Emits structured events: `("fatura", {...})` per extracted row (invoice no, company, amount, source, warnings, duration), `("atlandi", {...})`, `("isleniyor", {dosya, tip})` — the name and the type (`Dijital`/`OCR`/`XML`) travel in separate keys so the UI can match an in‑flight file against the `dosya` key of the later `fatura`/`atlandi` event; merged into one string the match breaks and the file stays "processing" forever (`tests/test_olay_sozlesmesi.py` guards this). **Does not write Excel** — when finished it emits a `("review", payload)` event (payload keys: `mevcut, yeni, atlanmis, uyarilar, cikti, kesildi`) so the GUI can show the review window before saving. Testable without a UI.
- **`review.py`** – Pure logic for the review/correction UI (no UI imports): `DUZENLENEBILIR_ALANLAR`, `satir_form_degerleri`, `form_satira_uygula` (converts form text back to typed values via `to_float`/`tarih_parse`, returns a copy), `nihai_satirlar` (final list = existing + non‑excluded new rows). Re‑validation reuses `veri_dogrula`.
- **`gemini.py`** – **The only door to the AI model.** Callers know one method: `istemci.metin_uret(parcalar) -> str`. Behind it live the RPM limiter, the retry ladder, and error classification; `extraction` and `worker` never import `google.genai`. `parcalar` is a list of `str` (text) and `bytes` (JPEG); Gemini's `Part` type never crosses the seam.
  - `ModelIstemcisi(client, *, bilgi, iptal, uyu, sinirlayici)` – `bilgi` is a plain callable (not a queue), so the module knows nothing about the UI event contract. `uyu`/`saat` are injected: testing the 15/30/45/60 s ladder with the real clock would take 225 seconds, i.e. it would never be tested.
  - `Sinirlayici` – RPM limiter. Its state is **process‑lifetime, not run‑lifetime** (`_VARSAYILAN_SINIRLAYICI`): the quota belongs to the API key, so stopping and restarting must not reset the counter or the second run instantly hits 429.
  - `olustur(api_key, *, bilgi, iptal)` – builds the real `genai.Client` and hides it behind the seam.
  - All model‑call constants live here: `GEMMA_MODEL`, `MAX_DENEME`, `TIMEOUT_SANIYE`, `RPM_LIMIT`, `THINKING_BUDGET`, `TEKRAR_HATALARI`, `API_KEY_HATALARI`.
- **`fatura.py`** – The invoice row's **schema** and its derived values. The row itself is still a plain `dict`.
  - `ALANLAR` – one `Alan` (NamedTuple) per field: Excel column/header/width, form label/type, `ogrenilir`. `SUTUN` (excel_utils), `DUZENLENEBILIR_ALANLAR` (review) and `OGRENILEN_ALANLAR` (duzeltme) are all **derived** from it — adding a field is one line. **Excel column numbers are written explicitly, not derived from list order**: old Excel files are read from those positions, so reordering the list must never move a column. `tests/test_fatura.py` pins the whole map.
  - `PROMPT_SABLON` and `veri_dogrula`'s field names stay out of the table on purpose: one is Turkish prose written for the model, the other is a different rule per field.
  - `kaynak(satir, bilinmeyen="")` / `dosya_adi(satir, bos="")` – derivations that used to be copied into `worker`, `api`, `excel_utils` and `ozet` (the `ozet` copy had already drifted to a `"Bilinmiyor"` default — hence the argument).
- **`hatalar.py`** – The exception taxonomy. Separate because the module that *raises* and the module that *catches* are usually different (`excel_utils` raises `ExcelHatasi`, `worker`/`api` catch it); without it, catchers import the raiser purely for an exception class.
- **`extraction.py`** – Core data‑extraction logic. Knows how to build a request and type the answer, **not** how to talk to a model. Contains:
  - `pdf_den_veri_cek(dosya, istemci, zoom, metin)` – Hybrid extraction: uses the `metin` arg if the caller already extracted the digital text (avoids double work), otherwise calls `pdf_text_ayikla`. If the text is > 100 chars, sends the raw text; otherwise falls back to JPEG images. Tags the result with `_teknik_bilgi` = `"Dijital"` or `"OCR"`.
  - `pdf_text_ayikla` – Extracts the embedded digital text layer from a PDF (empty string if none).
  - `_json_ayikla` – Robustly extracts a JSON object from the model reply, tolerating ``` fences and surrounding prose; raises `ModelHatasi` if no JSON object is found.
  - `xml_den_veri_cek` – Parses UBL XML invoices directly.
  - `veri_dogrula` – Validates extracted fields and returns **`[(alan, mesaj), ...]`** — the field name lets the review screen show each warning under the input it belongs to. A test enforces that every field name exists in `DUZENLENEBILIR_ALANLAR`, otherwise a warning would silently have nowhere to render. Includes an amount-consistency check: the implied VAT rate derived from `kdv_haric_tutar` and `vergiler_dahil_tutar` must match a known Turkish VAT rate (`KDV_ORANLARI = (0, 1, 8, 10, 18, 20)`, ±0.5 tolerance).
  - Rate limiting, retries and error classification are **not** here — they live behind `gemini.ModelIstemcisi`.
  - PDF image rendering with configurable zoom (1.0×–3.0×).
- **`ozet.py`** – Pure summary computation (`ozet_hesapla`): general, monthly, and per-company breakdowns with per-currency totals. No UI or openpyxl dependency — only plain Python and the extracted row data.
- **`duzeltme.py`** – Öğrenen düzeltme kuralları (saf mantık, arayüz/Excel'siz). VKN bazlı firma-sabit alan kuralları (`OGRENILEN_ALANLAR = ["sirket_adi", "vergi_dairesi"]`) için `kurallari_oku`/`kurallari_yaz`/`kural_uygula`/`kural_ekle`. Kurallar `duzeltmeler.json`'da tutulur (frozen modda AppData). `para_birimi` bilinçli olarak kapsam dışı (faturaya özel). Worker, çıkarılan her satıra `kural_uygula`'yı `veri_dogrula`'dan önce uygular; review ekranında "hatırla" kutusu satırları işaretler, `api.review_onayla` kaydeder.
- **`excel_utils.py`** – Reads/writes the output Excel file. Maintains a hidden column (O, col 15) with the full file path for robustness, and a visible “Kaynak” column (col 16) showing `Dijital`/`OCR`/`XML`. Creates HYPERLINK formulas for PDF files, plain “XML” labels for XML files. The hidden‑path column position is unchanged, so older Excel outputs remain readable. Also writes an auto-generated **”Özet” sheet** (second sheet; general totals, monthly and company breakdowns, per-currency) via `_ozet_sayfasi_yaz`; the main “Faturalar” sheet stays first/active so older outputs and `mevcut_verileri_oku` are unaffected.
- **`build.bat`** – One‑click EXE build script.

### Configuration and State
- **`.env`** – `GEMINI_API_KEY`, `TEMA` (`mocha`/`macchiato`/`frappe`/`nord`/`latte`/`kagit`), `KALITE` (zoom), `PENCERE` (`GxY` — size only; position is deliberately not saved because a remote‑desktop resolution change could put the window off‑screen), `KLASOR` (last folder). In EXE mode this file is stored in `%APPDATA%\FaturaAyiklayici`. A `.env.example` template ships in the repo.
- **`gecmis.json`** – Log of previous runs (folder, output file name, processed count, duration). Also stored in AppData when frozen.
- **`duzeltmeler.json`** – VKN bazlı öğrenen düzeltme kuralları. Frozen modda `%APPDATA%\FaturaAyiklayici`, değilse proje klasöründe.
- **`faturalar.xlsx`** – Example output file (can be deleted).

### Data‑safety rules (learned the hard way — a code review found all of these)
- **Never read the invoice sheet via `wb.active`.** Excel stores the last active tab; if the user
  saves while looking at “Özet”, that sheet's cells are read as invoices, `islenenmis` empties
  (every PDF is re‑sent to Gemini) and the next approval replaces months of history with garbage.
  Use `wb["Faturalar"]`.
- **Never `wb.save(target)` directly.** `_guvenli_kaydet` writes a `.tmp` and `os.replace`s it;
  a direct save truncates the target first, so an interrupted write destroys the archive.
  `kurallari_yaz` follows the same pattern.
- **An unreadable Excel must raise, not return empty.** Treating it as "no history" makes the next
  approval rewrite the file from scratch. `mevcut_verileri_oku` raises `ExcelHatasi`; `worker`
  catches it and stops.
- **`to_float` rule: when both separators are present, the LAST one is the decimal.**
  `1.234,56` and `1,234.56` both → `1234.56`. Dot‑only strings matching `\d{1,3}(\.\d{3})+`
  are thousands (`1.234` → 1234; this silently produced 1,234 before and the VAT check could not
  catch it because both amounts were corrupted identically).
- **`excel_olustur` must wrap every `OSError`, not just `PermissionError`** — a raw error escapes
  `api.py`'s `except ExcelHatasi`, reaches JS, and the review screen's “Onayla” button dies with
  the user's edits still unsaved.

### JS is a trust boundary
`web/` can call any public `Api` method with any argument. Guard on the Python side, not only in
the UI: `_satir()` checks `0 <= int(i) < len`, `basla()` refuses to start while `_calisiyor`
(a double‑click used to spawn a second worker and silently discard the first run's output along
with the Gemini quota it had spent). Disabling a button *after* `await` is too late.

### Async in the review screen
Every `await` in `review.js` is a point where the user may have selected another invoice. After
awaiting, re‑check `R.secili` before touching the DOM — otherwise the form shows invoice A while
the preview shows invoice B's document, and the user approves against the wrong page. Also never
rebuild the form with `innerHTML` on edit: it eats characters typed after Tab and drops focus.
`rvUyariGoster` updates warnings in place.

### Constants & Settings (gemini.py)
- `GEMMA_MODEL = "gemma-4-31b-it"` — **2026‑08‑01'de doğrulandı:** `client.models.list()` çıktısında var (`models/gemma-4-31b-it`) ve gerçek bir üretim çağrısı yanıt döndürüyor. Gemma modelleri JSON‑mode/`response_schema` desteklemediği için JSON güvenilirliği `_json_ayikla`'nın dayanıklı ayrıştırmasına dayanır.
- `MAX_DENEME = 5` – Retry attempts for transient API errors.
- `TIMEOUT_SANIYE = 180` – Request timeout.
- `MAX_WORKERS = 5` – Parallel PDF processing threads (this one lives in `extraction.py` — it is a worker concern, not a model concern).
- `RPM_LIMIT = 14` – Requests per minute (safe margin under the 15‑RPM free limit).
- `THINKING_BUDGET = -1` – Default Gemini thinking budget (unlimited).

### Data Flow
1. User selects a folder containing PDF and/or XML files.
2. Worker thread scans the folder, filters out already‑processed files (based on the existing Excel output).
3. PDF files are processed in parallel (`ThreadPoolExecutor`); XML files are processed sequentially.
4. Each PDF is processed with the hybrid method: if it has a usable digital text layer (> 100 chars) the text is sent to Gemini; otherwise it is rendered to JPEG images (zoom factor configurable via the UI) and sent as a vision request. The JSON response is parsed in both cases.
5. XML files are parsed with `xml.etree.ElementTree` using UBL namespaces.
6. Extracted data is validated (`veri_dogrula`); warnings are collected per row.
7. When processing finishes the worker emits `("review", payload)`. `api` keeps the typed rows in memory and sends the UI only a **text projection** (`satir_form_degerleri`) plus warnings and the field list, so `datetime`/`float` never round‑trip through JSON. The review screen shows, the user edits/excludes rows; each edit calls back `satir_dogrula` for fresh warnings.
8. On approval `review_onayla` converts the text back with `form_satira_uygula`, learns any "remember for this company" rules, and writes Excel. **Excel is written only after approval.** On cancel nothing is written. If the write fails (file locked) the screen stays open so edits aren't lost.
9. Progress and log events reach the UI through `log_q` → `_pompa` → `window.olaylar([...])`.

### Invoice‑Number Correction
- Turkish e‑invoice standard: 3 uppercase letters/digits + 4‑digit year + 9‑digit sequence (16 characters total).
- Gemini sometimes adds an extra **leading** zero to the sequence, making 17 characters. `_duzelt_fatura_no` detects the pattern `[A‑Z0‑9]{3}\d{14}` and strips a leading zero from the sequence part **only**. If the sequence has no leading zero, the number is left untouched (we don't guess which interior digit is extra — corrupting a valid number is worse than a warning).
- The correction is applied automatically after both PDF and XML extraction; `veri_dogrula` warns if the length is still not 16.

## UI & Styling

The UI is HTML/CSS/JS under `web/`. There is **one window**; the review screen is a hidden
`<div class="rv">` that replaces the main screen when needed.

### Themes
Six themes, each a single variable block in `tema.css`: **mocha** (default), **macchiato**,
**frappe**, **nord** (dark) and **latte**, **kagit** (light). Adding a theme = copy a block and
change the colours; no other file changes. `tema.js` builds the picker from its own `TEMALAR`
list, and the choice is persisted via `api.tema_kaydet` → `.env`.

**Never hard‑code a colour.** Always use the variables: `--bg --panel --card --raised --line
--line-soft --tx --sub --dim --accent --accent-2 --on-accent --ok --warn --err` plus the
`*-bg` tints, `--focus` and `--shadow`. A literal hex will break five of the six themes.
`--on-accent` exists because text on the accent colour must be dark in dark themes and white
in light ones.

### Layout rules that were decided deliberately
- Main screen is capped at **1000px** and centred; full‑width was tried and rejected (long gaps
  between a file name and its duration make rows hard to track).
- Vertically, only the log grows (`.body>*:not(.feed){flex-shrink:0}`); settings stay put.
- The review screen is full width. Under 1020px the PDF preview column hides — it is unreadable
  at that size.
- Sizing that belongs to a context goes on the context, not the component: `.actions
  .btn-primary{flex:1}`, **not** `.btn-primary{flex:1}`. The latter broke the same button inside
  modals.

### Dialogs
- **Never use `confirm()`/`alert()`** — WebView2 titles them “127.0.0.1:… diyor ki”, which looks
  broken. Use `onayModal(baslik, mesaj, evetEtiket, tehlikeli)` and `bilgiModal(baslik, mesaj)`
  in `app.js`; both return promises and close on Escape / outside click.
- Modals are built with the `modal(html, genis)` helper and follow the theme automatically.

### Behaviour notes
- The status card merges progress and totals into one block; during a run it shows
  `işlenen / toplam`, ETA, and the success/warning/skip breakdown with per‑currency totals.
- The log feed shows **newest first**; “işleniyor” is not a feed row, it updates the status
  card. With `MAX_WORKERS = 5` several files are in flight at once, so the card lists **all**
  of them (`#stUcan`, two columns) — a single line silently showed whichever started last.
  The pre‑pywebview tkinter UI logged each start as a feed row; that was dropped deliberately.
- Status‑card headlines are written **Title Case in the source**, not via CSS
  `text-transform:capitalize` — that rule is locale‑naive and turns “işleniyor” into
  “Işleniyor” (dotless I) depending on the engine.
- The review form has **no “Apply” button** — leaving a field applies and re‑validates it. The old
  tkinter screen required Apply and silently discarded edits when users forgot.
- PDF preview: `api.onizleme` renders with `fitz` at the requested zoom and returns base64 PNG.
  `.pv img` must **not** have `max-width` — that silently cancels zoom by scaling the larger image
  back down. On selecting an invoice the page is fitted to the panel width.

## Error Handling

### Custom Exceptions (hatalar.py)
- `APIKeyHatasi` – Invalid/missing API key; stops the entire job.
- `InternetHatasi` – Connection/rate‑limit issues; skips the current file.
- `PDFHatasi` / `XMLHatasi` – Corrupted or unreadable file; skips the file.
- `ModelHatasi` – Invalid/unparseable JSON response from the AI model; skips the file.
- `ExcelHatasi` – Permission error when saving Excel; warns but continues.

### Retry Logic
- Network/timeout/429/503 errors trigger a retry with backoff (15/30/45/60/75 s, up to `MAX_DENEME` attempts) **inside `gemini.ModelIstemcisi`**; callers see either a result or a classified exception. If the reply carries its own `retry in Ns`, that wins over the ladder.
- API‑key errors are not retried; the UI opens the API‑key modal.

## Git & Commit Conventions

- Commit messages are in Turkish.
- Format: a short summary line followed by bullet‑point details (if needed).
- The repository is at `https://github.com/Javerto/Fatura-Ayiklama` (master branch).

## References

- Memory files in `.claude/projects/…/memory/` provide user preferences and past decisions, but they may be outdated; always verify against the current code.
- The `build.bat` script is the single source of truth for EXE packaging.
- For prompt engineering, see `PROMPT_SABLON` in `extraction.py` (Turkish instructions for Gemini).

## Tips for Development

- When modifying UI, test both development mode (`python main.py`) and EXE mode (run the built executable).
- The application uses `sys.frozen` to detect EXE mode and change config/file paths accordingly.
- All file paths should be handled with `pathlib` for cross‑platform consistency (though the target is Windows).
- Adding new configuration options should consider both development and frozen environments (store in AppData when frozen).
- New dialogs: use `onayModal`/`bilgiModal`; never `confirm`/`alert`, never a literal colour.
- **Verify in the running app, not just in pytest.** The UI layer is where the real bugs were.
- A guard test is worth writing only if you've seen it fail: put the bug back, watch the test go
  red, then remove it. `test_main_pencereyi_genel_nitelige_atamaz` was written this way after the
  older `test_api.py` turned out to miss the very regression its docstring claimed to cover.
