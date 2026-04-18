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
- **File formats**: PDF (image‑based extraction), XML (UBL e‑invoice parsing)
- **Output**: Excel with validation, warnings, and clickable file links

## Development Commands

### Dependencies
```bash
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
There are no automated test suites yet. The user expects both **visual testing** (run the GUI and verify UI behavior) and **unit testing** (mock tkinter imports and test logic). For unit tests, patch internal imports (e.g., `gui.pdf_den_veri_cek`, not `extraction.pdf_den_veri_cek`) because of intra‑module imports.

## Architecture

### Module Responsibilities
- **`main.py`** – Entry point; creates tkinter root and launches the `App` class from `gui.py`.
- **`gui.py`** – Tkinter interface and background worker thread. Handles folder selection, API‑key input, progress logging, and error display. Uses a queue to communicate with the worker.
- **`extraction.py`** – Core data‑extraction logic. Contains:
  - `pdf_den_veri_cek` – Converts PDF pages to images, sends them to Gemini, parses the JSON response.
  - `xml_den_veri_cek` – Parses UBL XML invoices directly.
  - `veri_dogrula` – Validates extracted fields and returns a list of warnings.
  - Rate limiter (`_rpm_bekle`) – Ensures ≤ 14 requests per minute (Gemini free‑tier limit).
  - PDF image rendering with configurable zoom (1.0×–3.0×).
- **`excel_utils.py`** – Reads/writes the output Excel file. Maintains a hidden column (O) with the full file path for robustness. Creates HYPERLINK formulas for PDF files, plain “XML” labels for XML files.
- **`build.bat`** – One‑click EXE build script.

### Configuration and State
- **`.env`** – Contains `GEMINI_API_KEY`. In EXE mode this file is stored in `%APPDATA%\FaturaAyiklayici`.
- **`gecmis.json`** – Log of previous runs (folder, output file name, processed count, duration). Also stored in AppData when frozen.
- **`faturalar.xlsx`** – Example output file (can be deleted).

### Constants & Settings (extraction.py)
- `GEMMA_MODEL = "gemma-4-31b-it"`
- `MAX_DENEME = 5` – Retry attempts for transient API errors.
- `TIMEOUT_SANIYE = 180` – Request timeout.
- `MAX_WORKERS = 5` – Parallel PDF processing threads.
- `RPM_LIMIT = 14` – Requests per minute (safe margin under the 15‑RPM free limit).
- `THINKING_BUDGET = -1` – Default Gemini thinking budget (unlimited).

### Data Flow
1. User selects a folder containing PDF and/or XML files.
2. Worker thread scans the folder, filters out already‑processed files (based on the existing Excel output).
3. PDF files are processed in parallel (`ThreadPoolExecutor`); XML files are processed sequentially.
4. Each PDF is converted to JPEG images (zoom factor configurable via the UI), sent to Gemini with a Turkish prompt, and the JSON response is parsed.
5. XML files are parsed with `xml.etree.ElementTree` using UBL namespaces.
6. Extracted data is validated (`veri_dogrula`); warnings are collected and shown at the end via a “⚠ Uyarılar” button.
7. Validated rows are appended to the Excel file (existing rows are preserved).
8. Progress, success, skip, and error messages are relayed to the UI via a queue.

### Invoice‑Number Correction
- Turkish e‑invoice standard: 3 uppercase letters/digits + 4‑digit year + 9‑digit sequence (16 characters total).
- Gemini sometimes adds an extra zero, making 17 characters. `_duzelt_fatura_no` detects the pattern `[A‑Z0‑9]{3}\d{14}` and removes the first zero from the sequence part.
- The correction is applied automatically after both PDF and XML extraction; `veri_dogrula` warns if the length is still not 16.

## UI & Styling

### Color Palette (Catppuccin Mocha)
All UI elements must use these hex constants (defined at the top of `gui.py`):
- `BG = "#1e1e2e"` – Window background
- `MANTLE = "#181825"` – Popup background
- `SURFACE = "#313244"` – Button background
- `TEXT = "#cdd6f4"` – Primary text
- `SUBTEXT = "#a6adc8"` – Secondary text
- `BLUE = "#89b4fa"` – Headers, active elements
- `GREEN = "#a6e3a1"` – Success messages
- `RED = "#f38ba8"` – Errors
- `OVERLAY = "#6c7086"` – Disabled state

### Popup Design
- **Never use `tkinter.OptionMenu`** – it crashes the application on double‑click in Windows. Instead, create a button that opens a `Toplevel` popup with a list of options (see `_kalite_popup` and `_ask_api_key_popup` for reference).
- Popups should follow the Mocha palette: `MANTLE` background, `BLUE` title, `SUBTEXT` description, `SURFACE` buttons.
- Icons are embedded as base64‑encoded PNG (see `_ICON_B64` in `gui.py`).

### Widget Notes
- The main window uses a `Text` widget for logging with colored tags (`"ok"`, `"warn"`, `"skip"`, `"info"`, `"critical"`).
- A “Kalite/Zoom” button lets the user choose image zoom (1.0×, 1.5× default, 2.0×, 3.0×) for PDF extraction.
- An “⚠ Uyarılar” button appears after processing if any validation warnings were collected, showing a scrollable list.

## Error Handling

### Custom Exceptions (extraction.py)
- `APIKeyHatasi` – Invalid/missing API key; stops the entire job.
- `InternetHatasi` – Connection/rate‑limit issues; skips the current file.
- `PDFHatasi` / `XMLHatasi` – Corrupted or unreadable file; skips the file.
- `ExcelHatasi` – Permission error when saving Excel; warns but continues.

### Retry Logic
- Network/timeout/429/503 errors trigger a retry with exponential backoff (up to `MAX_DENEME` attempts).
- API‑key errors are not retried; they show a popup asking for a new key.

## Git & Commit Conventions

- Commit messages are in Turkish.
- Format: a short summary line followed by bullet‑point details (if needed).
- Include `Co‑Authored‑By: Claude Opus 4.6 <noreply@anthropic.com>`.
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

# Model Bilgisi
- DeepSeek kullanılıyor, token limiti 102400
- Bağlam %70'e ulaştığında beni uyar
- %80'e ulaştığında otomatik /compact yap