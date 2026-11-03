# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
pip install google-genai pymupdf python-dotenv openpyxl pywebview lxml
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
- Hidden imports: `fitz`, `openpyxl`, `dotenv`, `lxml.etree`, `clr_loader`

CI (`.github/workflows/exe.yml`) builds the same script on every PR and master push, runs `FaturaAyiklayici.exe --saglik` (imports everything including the lazy WinForms layer, checks `web/`, writes the reason to `%TEMP%\FaturaAyiklayici-saglik.txt`, exits without a window) and uploads the EXE as an artifact (30 days). It catches packaging breakage only; look, real login and reCAPTCHA still need a person. `pymupdf` stays below 2.0: 2.0 pulls a 50 MB layout model and onnxruntime, and the EXE crashes at startup on the missing model file. The resulting EXE is placed in `dist/FaturaAyiklayici.exe`. Configuration files (`.env`, `gecmis.json`) are stored in `%APPDATA%\FaturaAyiklayici` when running as EXE, otherwise in the project folder.

### Testing
A pytest suite lives in `tests/` (config in `pytest.ini`, `pythonpath = .`). Run it with:
```bash
python -m pytest          # tüm testler
python -m pytest tests/test_xml.py -q   # tek dosya
python -m pytest -k fatura_no           # isim filtresiyle
```
Run in CI on every push/PR (`.github/workflows/test.yml`). The runner is **windows-latest**, not Linux: `api.py` imports `webview` at module level and the app is Windows‑only anyway (`os.startfile`, WebView2) — a Linux runner would be a guess. Coverage focuses on the pure, UI‑free logic: `_duzelt_fatura_no`, `_json_ayikla`, `to_float`, `tarih_parse`, `veri_dogrula`, the Excel URL/round‑trip helpers, `xml_den_veri_cek` (via `tests/fixtures/ornek_fatura.xml`), the Excel "Kaynak" column, and end‑to‑end `worker` runs for **both** the XML and the PDF path — the PDF path became testable once the model call moved behind the `gemini` seam (`worker(..., istemci=<sahte>)`, no network, no `google.genai` patching). `tests/test_gemini.py` pins the resilience contract: backoff ladder, `retry in Ns` override, API‑key errors never retried (against Google's real error text), unknown errors re‑raised raw, cancellation mid‑sleep, and the RPM limiter. Time is injected (`uyu`/`saat`) — with the real clock the ladder alone would take 225 seconds. It also covers `Api` (only callable public attributes — see below), `pencere_boyutu`, `review_onayla` (`tests/test_review_onayla.py` — the only path that writes Excel), and the **Python↔JS event contract** (`tests/test_olay_sozlesmesi.py`). `Api(kok=<path>)` takes the config directory per instance, so tests never touch the real `.env` / `gecmis.json` / `duzeltmeler.json` / `alanlar.json`. `pytest.ini` filters third‑party `DeprecationWarning`s so output stays clean.

CI runs `ruff check --select F .` before pytest. Mechanical code rules (no `confirm`/`alert`, no literal colour, no `wb.active` on a loaded workbook, `save` only inside `_guvenli_kaydet`) are tests in `tests/test_kurallar.py`; judgement rules for review live in `CODING_STANDARDS.md`.

**Accuracy is measured separately from correctness.** pytest pins the logic; it says nothing about how well the model reads an invoice. `altin.py` runs a hand‑verified golden set through the **real** model and prints per‑field accuracy (`python altin.py`, `--olustur` drafts the expected JSONs for you to correct by hand). The invoices live in `altin/` — gitignored, they are real customer data — and each one sits next to a same‑named `.json` holding only the fields you vouched for. Never change the prompt or the model without a before/after run. The script is not a test because it costs API quota and needs the network; only its comparison logic is pinned (`tests/test_altin.py`).

**Headless tests cannot catch UI‑layer bugs.** Three real defects during the pywebview migration were invisible to pytest: the startup hang (needed a real `Window` object), the dead‑UI race, and zoom looking broken (CSS shrank a correctly‑enlarged PNG). Always launch the app and have the user look. `py-spy dump --pid <pid>` is the tool for a frozen window. When testing code that does intra‑module imports, patch where the name is used (e.g. `worker.pdf_text_ayikla`), not where it is defined.

## Architecture

Module responsibilities, configuration/state files, model constants, data flow, invoice-number correction and the exception taxonomy live in `docs/mimari.md`. Read the module's entry there before changing a module.

- ⚠ **All internal state of `Api` (`api.py`) must be `_`‑prefixed.** pywebview recurses into every public attribute of the api object (`webview/util.py::get_functions`) to build the JS proxy; a public `Window` reference makes it walk `pencere.native.AccessibilityObject.Bounds.Empty…` forever and the app hangs on startup. `tests/test_api.py` guards this.

## UI

Before touching `web/`, read `docs/arayuz.md`: theme variables, deliberate layout decisions, dialogs, review-screen async rules and behaviour notes.

## Data‑safety rules (learned the hard way — a code review found all of these)
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

## JS is a trust boundary
`web/` can call any public `Api` method with any argument. Guard on the Python side, not only in
the UI: `_satir()` checks `0 <= int(i) < len`, `basla()` refuses to start while `_calisiyor`
(a double‑click used to spawn a second worker and silently discard the first run's output along
with the Gemini quota it had spent). Disabling a button *after* `await` is too late.

## Git & Commit Conventions

- Commit messages are in Turkish.
- Format: a short summary line followed by bullet‑point details (if needed).
- The repository is at `https://github.com/Javerto/fatura-ayiklayici` (master branch).

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` (the domain glossary) plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## References

- Memory files in `.claude/projects/…/memory/` provide user preferences and past decisions, but they may be outdated; always verify against the current code.
- The `build.bat` script is the single source of truth for EXE packaging.
- For prompt engineering: the fixed header is `PROMPT_BASLIK` in `sema.py`, per-field text is each field's `aciklama` in the schema (seed: `sema.TOHUM`).

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
