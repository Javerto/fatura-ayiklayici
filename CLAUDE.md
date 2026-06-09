# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Dil Kuralı
- ALWAYS respond in Turkish (Türkçe).
- Tüm açıklamalar, commit mesajları ve yorumlar Türkçe olmalı.
- Kod içindeki değişken/fonksiyon isimleri İngilizce kalabilir ama kullanıcıyla iletişim her zaman Türkçe olmalı.

## Overview

Fatura Ayıklayıcı is a Turkish-language desktop application for extracting invoice data from PDF/XML e-invoices using Google's Gemini AI. The application is built with Python/tkinter and designed for non‑technical users. It outputs a formatted Excel file with hyperlinks to source documents.

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
pip install google-genai pymupdf python-dotenv openpyxl
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
- `--collect-all google.genai`
- Hidden imports: `fitz`, `openpyxl`, `dotenv`

The resulting EXE is placed in `dist/FaturaAyiklayici.exe` (~41 MB). Configuration files (`.env`, `gecmis.json`) are stored in `%APPDATA%\FaturaAyiklayici` when running as EXE, otherwise in the project folder.

### Testing
A pytest suite lives in `tests/` (config in `pytest.ini`, `pythonpath = .`). Run it with:
```bash
python -m pytest          # tüm testler
python -m pytest tests/test_xml.py -q   # tek dosya
python -m pytest -k fatura_no           # isim filtresiyle
```
Coverage focuses on the pure, tkinter‑free logic: `_duzelt_fatura_no`, `_json_ayikla`, `to_float`, `tarih_parse`, `veri_dogrula`, the Excel URL/round‑trip helpers, `xml_den_veri_cek` (via `tests/fixtures/ornek_fatura.xml`), the Excel "Kaynak" column, and an end‑to‑end `worker` smoke test (XML‑only, `google.genai.Client` patched). `pytest.ini` filters third‑party `DeprecationWarning`s so output stays clean. The user also values **visual testing** — running the GUI to verify UI behavior. When testing code that does intra‑module imports, patch where the name is used (e.g. `worker.pdf_text_ayikla`), not where it is defined.

## Architecture

### Module Responsibilities
- **`main.py`** – Entry point; creates tkinter root and launches the `App` class from `gui.py`.
- **`gui.py`** – Tkinter interface only. Handles folder selection, API‑key input, progress logging, theming, and error display. Spawns the worker on a background thread and talks to it via a queue. **No extraction/Excel logic lives here** — it imports `worker` from `worker.py`.
- **`worker.py`** – The background processing loop (`worker(...)`). UI‑independent pure logic: scans the folder, runs PDF tasks in a `ThreadPoolExecutor`, processes XML‑only files sequentially, and reports progress through the `log_q` queue and `stop_event`. **Does not write Excel** — when finished it emits a `("review", payload)` event (payload keys: `mevcut, yeni, atlanmis, uyarilar, cikti, kesildi`) so the GUI can show the review window before saving. Testable without tkinter.
- **`review.py`** – Pure logic for the review/correction UI (no tkinter): `DUZENLENEBILIR_ALANLAR`, `satir_form_degerleri`, `form_satira_uygula` (converts form text back to typed values via `to_float`/`tarih_parse`, returns a copy), `nihai_satirlar` (final list = existing + non‑excluded new rows). Re‑validation reuses `veri_dogrula`.
- **`review_ui.py`** – `ReviewWindow` (Toplevel): a master‑detail review/edit screen shown before Excel is written. Top table of new invoices (warned rows highlighted), an editable form for the selected invoice with live warning refresh on "Uygula", row exclusion, jump‑to‑warning, and an **embedded PDF preview** (`fitz` → base64 PNG → `tk.PhotoImage`, zoom/page nav, "Dışarıda Aç"). The colour palette is passed in as a dict (avoids a circular import with `gui.py`). On confirm it calls back `on_confirm(nihai, uyarilar) -> bool`; on cancel `on_cancel()`.
- **`extraction.py`** – Core data‑extraction logic. Contains:
  - `pdf_den_veri_cek` – Hybrid extraction: uses the `metin` arg if the caller already extracted the digital text (avoids double work), otherwise calls `pdf_text_ayikla`. If the text is > 100 chars, sends the raw text to Gemini; otherwise falls back to JPEG images. Tags the result with `_teknik_bilgi` = `"Dijital"` or `"OCR"`.
  - `pdf_text_ayikla` – Extracts the embedded digital text layer from a PDF (empty string if none).
  - `_json_ayikla` – Robustly extracts a JSON object from the model reply, tolerating ``` fences and surrounding prose; raises `ModelHatasi` if no JSON object is found.
  - `xml_den_veri_cek` – Parses UBL XML invoices directly.
  - `veri_dogrula` – Validates extracted fields and returns a list of warnings.
  - Rate limiter (`_rpm_bekle`) – Ensures ≤ 14 requests per minute (Gemini free‑tier limit).
  - PDF image rendering with configurable zoom (1.0×–3.0×).
- **`excel_utils.py`** – Reads/writes the output Excel file. Maintains a hidden column (O, col 15) with the full file path for robustness, and a visible "Kaynak" column (col 16) showing `Dijital`/`OCR`/`XML`. Creates HYPERLINK formulas for PDF files, plain “XML” labels for XML files. The hidden‑path column position is unchanged, so older Excel outputs remain readable.
- **`build.bat`** – One‑click EXE build script.

### Configuration and State
- **`.env`** – Contains `GEMINI_API_KEY` and `TEMA` (`dark`/`light`). In EXE mode this file is stored in `%APPDATA%\FaturaAyiklayici`. A `.env.example` template ships in the repo.
- **`gecmis.json`** – Log of previous runs (folder, output file name, processed count, duration). Also stored in AppData when frozen.
- **`faturalar.xlsx`** – Example output file (can be deleted).

### Constants & Settings (extraction.py)
- `GEMMA_MODEL = "gemma-4-31b-it"` — **Doğrulanmalı:** bu model adının `google-genai` üzerinden gerçekten erişilebilir olduğundan emin olun (`client.models.list` veya küçük bir test çağrısıyla). Geçersizse tüm PDF çıkarmaları başarısız olur. Gemma modelleri JSON‑mode/`response_schema` desteklemediği için JSON güvenilirliği `_json_ayikla`'nın dayanıklı ayrıştırmasına dayanır.
- `MAX_DENEME = 5` – Retry attempts for transient API errors.
- `TIMEOUT_SANIYE = 180` – Request timeout.
- `MAX_WORKERS = 5` – Parallel PDF processing threads.
- `RPM_LIMIT = 14` – Requests per minute (safe margin under the 15‑RPM free limit).
- `THINKING_BUDGET = -1` – Default Gemini thinking budget (unlimited).

### Data Flow
1. User selects a folder containing PDF and/or XML files.
2. Worker thread scans the folder, filters out already‑processed files (based on the existing Excel output).
3. PDF files are processed in parallel (`ThreadPoolExecutor`); XML files are processed sequentially.
4. Each PDF is processed with the hybrid method: if it has a usable digital text layer (> 100 chars) the text is sent to Gemini; otherwise it is rendered to JPEG images (zoom factor configurable via the UI) and sent as a vision request. The JSON response is parsed in both cases.
5. XML files are parsed with `xml.etree.ElementTree` using UBL namespaces.
6. Extracted data is validated (`veri_dogrula`); warnings are collected per row.
7. When processing finishes the worker emits `("review", payload)`; the GUI opens `ReviewWindow`. The user edits/excludes rows and approves. **Excel is written only after approval** via `excel_olustur` (existing rows preserved). On cancel nothing is written. If a write fails (file locked) the window stays open so edits aren't lost.
8. Progress, success, skip, and error messages are relayed to the UI via a queue.

### Invoice‑Number Correction
- Turkish e‑invoice standard: 3 uppercase letters/digits + 4‑digit year + 9‑digit sequence (16 characters total).
- Gemini sometimes adds an extra **leading** zero to the sequence, making 17 characters. `_duzelt_fatura_no` detects the pattern `[A‑Z0‑9]{3}\d{14}` and strips a leading zero from the sequence part **only**. If the sequence has no leading zero, the number is left untouched (we don't guess which interior digit is extra — corrupting a valid number is worse than a warning).
- The correction is applied automatically after both PDF and XML extraction; `veri_dogrula` warns if the length is still not 16.

## UI & Styling

### Color Palette (Catppuccin – dual theme)
The app ships **two palettes**: `_KARANLIK` (Catppuccin Mocha, dark) and `_AYDINLIK` (Catppuccin Latte, light). The active palette is exposed through **module‑level globals** (`BG`, `MANTLE`, `SURFACE`, `TEXT`, `SUBTEXT`, `BLUE`, `GREEN`, `RED`, `OVERLAY`), set by `_tema_uygula(karanlik: bool)`. Never hard‑code hex values in widgets — always read these globals so both themes work.

- The user toggles theme via the `🌙/☀` button (`_tema_degistir`), which re‑applies the palette, rebuilds the UI (destroys and recreates all widgets), and persists the choice as `TEMA=dark|light` in `.env`.
- `_tema_uygula` must be called **before** `_build_ui` (done in `__init__` after loading `.env`).

Dark (Mocha) reference values: `BG=#1e1e2e`, `MANTLE=#181825`, `SURFACE=#313244`, `TEXT=#cdd6f4`, `SUBTEXT=#a6adc8`, `BLUE=#89b4fa`, `GREEN=#a6e3a1`, `RED=#f38ba8`, `OVERLAY=#6c7086`.

### Popup Design
- **Never use `tkinter.OptionMenu`** – it crashes the application on double‑click in Windows. Instead, create a button that opens a `Toplevel` popup with a list of options (see `_kalite_popup` and `_ask_api_key_popup` for reference).
- Popups should follow the Mocha palette: `MANTLE` background, `BLUE` title, `SUBTEXT` description, `SURFACE` buttons.
- Icons are embedded as base64‑encoded PNG (see `_ICON_B64` in `gui.py`).

### Widget Notes
- The main window uses a `Text` widget for logging with colored tags (`"ok"`, `"warn"`, `"skip"`, `"info"`, `"critical"`, `"done_ok"`).
- A “Kalite/Zoom” button lets the user choose image zoom (1.0×, 1.5× default, 2.0×, 3.0×) for OCR fallback PDF extraction.
- An “⚠ Uyarılar” button appears after processing if any validation warnings were collected, showing a scrollable list.
- An “↺ Yeniden Dene” button re‑runs only the skipped files from the last run (`worker(..., retry_dosyalar=...)`).
- A “📋 Geçmiş” button shows run history from `gecmis.json` (last 20 runs).

## Error Handling

### Custom Exceptions (extraction.py)
- `APIKeyHatasi` – Invalid/missing API key; stops the entire job.
- `InternetHatasi` – Connection/rate‑limit issues; skips the current file.
- `PDFHatasi` / `XMLHatasi` – Corrupted or unreadable file; skips the file.
- `ModelHatasi` – Invalid/unparseable JSON response from the AI model; skips the file.
- `ExcelHatasi` – Permission error when saving Excel; warns but continues.

### Retry Logic
- Network/timeout/429/503 errors trigger a retry with exponential backoff (up to `MAX_DENEME` attempts).
- API‑key errors are not retried; they show a popup asking for a new key.

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
- If you add a new popup, copy the style from `_kalite_popup` and use the color constants; never hard‑code hex values.
