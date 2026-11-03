# Arayüz (`web/`)

CLAUDE.md'den taşındı. `web/` altında çalışırken geçerli kurallar.

The UI is HTML/CSS/JS under `web/`. There is **one window**; the review screen is a hidden
`<div class="rv">` that replaces the main screen when needed.

## Themes
Six themes, each a single variable block in `tema.css`: **mocha** (default), **macchiato**,
**frappe**, **nord** (dark) and **latte**, **kagit** (light). Adding a theme = copy a block and
change the colours; no other file changes. `tema.js` builds the picker from its own `TEMALAR`
list, and the choice is persisted via `api.tema_kaydet` → `.env`.

**Never hard‑code a colour.** Always use the variables: `--bg --panel --card --raised --line
--line-soft --tx --sub --dim --accent --accent-2 --on-accent --ok --warn --err` plus the
`*-bg` tints, `--focus` and `--shadow`. A literal hex will break five of the six themes.
`--on-accent` exists because text on the accent colour must be dark in dark themes and white
in light ones.

## Layout rules that were decided deliberately
- Main screen is capped at **1000px** and centred; full‑width was tried and rejected (long gaps
  between a file name and its duration make rows hard to track).
- Vertically, only the log grows (`.body>*:not(.feed){flex-shrink:0}`); settings stay put.
- The review screen is full width. Under 1020px the PDF preview column hides — it is unreadable
  at that size.
- Sizing that belongs to a context goes on the context, not the component: `.actions
  .btn-primary{flex:1}`, **not** `.btn-primary{flex:1}`. The latter broke the same button inside
  modals.

## Dialogs
- **Never use `confirm()`/`alert()`** — WebView2 titles them “127.0.0.1:… diyor ki”, which looks
  broken. Use `onayModal(baslik, mesaj, evetEtiket, tehlikeli)` and `bilgiModal(baslik, mesaj)`
  in `app.js`; both return promises and close on Escape / outside click.
- Modals are built with the `modal(html, genis)` helper and follow the theme automatically.

## Behaviour notes
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
- Row order: warned rows first, sorted **only on open** — re‑sorting during edits would move a row out from under the user. Keyboard: Alt+↑/↓ row, Alt+H exclude, Ctrl+Enter approve.
- `rvSatirSec` must blur before changing `R.secili`: rebuilding the form with focus inside fires `focusout`, and `rvUygula` would then write the old row's text into the new row.
- Field highlight: entering a field calls `api.deger_bul`. PDF → `extraction.pdf_deger_bul` returns boxes as page ratios, drawn over the image in percent so zoom needs no new call. XML → Python returns only the search forms and `rvXmlVurguCiz` marks text inside the frame. `R.vurgu`: `null` none searched, `{}` not found.
- XML preview: `extraction.xml_gorunumu` runs the XSLT embedded in the invoice through **lxml, not the browser's `XSLTProcessor`** (Chromium is removing it). The template comes from the issuer and is foreign code: entities, network and file access are off, `xsl:include/import` is refused (access control applies only during the transform). `rvXmlGoster` shows the output in `<iframe sandbox="allow-same-origin">` with a CSP prepended through `DOMParser`, so scripts cannot run and nothing is fetched. Scripted parts of a template (e.g. a QR code) therefore do not appear. No template → message + "Dışarıda aç".
- PDF preview: `api.onizleme` renders with `fitz` at the requested zoom and returns base64 PNG. The open document is shared by parallel bridge calls: use it only under `_pdf_kilit`. Await `img.decode()` before measuring the image: its size is 0 until then.
  `.pv img` must **not** have `max-width` — that silently cancels zoom by scaling the larger image
  back down. On selecting an invoice the page is fitted to the panel width.

## Async in the review screen
Every `await` in `review.js` is a point where the user may have selected another invoice. After
awaiting, re‑check `R.secili` before touching the DOM — otherwise the form shows invoice A while
the preview shows invoice B's document, and the user approves against the wrong page. Also never
rebuild the form with `innerHTML` on edit: it eats characters typed after Tab and drops focus.
`rvUyariGoster` updates warnings in place.
