"""
Arayüz ve arka plan işleme modülü.
"""

import json
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
from dotenv import load_dotenv, set_key
import concurrent.futures
import glob, os, pathlib, sys, threading, queue, time

import google.genai as genai

from extraction import (
    xml_den_veri_cek, pdf_den_veri_cek,
    APIKeyHatasi, InternetHatasi, PDFHatasi, XMLHatasi,
    ModelHatasi,
    TIMEOUT_SANIYE, MAX_WORKERS, veri_dogrula,
    pdf_gecerli_mi,
)
from excel_utils import mevcut_verileri_oku, excel_olustur, ExcelHatasi

# EXE modunda .env ve gecmis.json AppData'ya yazılır (kullanıcı görmez/silemez).
# Geliştirme modunda proje klasörüne yazılır.
if getattr(sys, "frozen", False):
    _BASE = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / "FaturaAyiklayici"
    _BASE.mkdir(parents=True, exist_ok=True)
else:
    _BASE = pathlib.Path(__file__).parent

ENV_DOSYASI    = _BASE / ".env"
GECMIS_DOSYASI = _BASE / "gecmis.json"

VERSION = "1.0"

# Fatura belgesi ikonu (32x32 RGBA PNG, şeffaf arka plan, base64)
_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAWElEQVR42mNgGAWDFeiHTPtP"
    "Lh51wIA7YMGuF/8H3AEUO4IaDqDIEdRyANmOoMQBVEmYow5A1gwEd/Dh0SgYTQPEpI3RKBhN"
    "A6NRMOqAUQeMOmC0r4kLAAAnW4FDe82NqwAAAABJRU5ErkJggg=="
)

# ─── RENK PALETLERİ ───────────────────────────────────────────────────────────
_KARANLIK = {   # Catppuccin Mocha
    "BG": "#1e1e2e", "MANTLE": "#181825", "SURFACE": "#313244",
    "TEXT": "#cdd6f4", "SUBTEXT": "#a6adc8", "BLUE": "#89b4fa",
    "GREEN": "#a6e3a1", "RED": "#f38ba8", "OVERLAY": "#6c7086",
}
_AYDINLIK = {   # Catppuccin Latte
    "BG": "#eff1f5", "MANTLE": "#e6e9ef", "SURFACE": "#ccd0da",
    "TEXT": "#4c4f69", "SUBTEXT": "#6c6f85", "BLUE": "#1e66f5",
    "GREEN": "#40a02b", "RED": "#d20f39", "OVERLAY": "#9ca0b0",
}

def _tema_uygula(karanlik: bool):
    """Palet global değişkenlerini günceller. _build_ui'den önce çağrılmalı."""
    global BG, MANTLE, SURFACE, TEXT, SUBTEXT, BLUE, GREEN, RED, OVERLAY
    p = _KARANLIK if karanlik else _AYDINLIK
    BG, MANTLE, SURFACE = p["BG"], p["MANTLE"], p["SURFACE"]
    TEXT, SUBTEXT = p["TEXT"], p["SUBTEXT"]
    BLUE, GREEN, RED, OVERLAY = p["BLUE"], p["GREEN"], p["RED"], p["OVERLAY"]

# Başlangıç teması (koyu) — __init__'te .env'den yeniden yüklenir
BG      = _KARANLIK["BG"]
MANTLE  = _KARANLIK["MANTLE"]
SURFACE = _KARANLIK["SURFACE"]
TEXT    = _KARANLIK["TEXT"]
SUBTEXT = _KARANLIK["SUBTEXT"]
BLUE    = _KARANLIK["BLUE"]
GREEN   = _KARANLIK["GREEN"]
RED     = _KARANLIK["RED"]
OVERLAY = _KARANLIK["OVERLAY"]
# ─────────────────────────────────────────────────────────────────────────────


# ─── ARKA PLAN WORKER ─────────────────────────────────────────────────────────

def worker(api_key: str, klasor: str, cikti_adi: str, log_q: queue.Queue,
           stop_event: threading.Event, retry_dosyalar: list | None = None,
           zoom: float = 1.5):
    """Fatura işleme döngüsü — ayrı thread'de çalışır."""

    def log(tag, mesaj):
        log_q.put((tag, mesaj))

    try:
        client = genai.Client(
            api_key=api_key,
            http_options={"timeout": TIMEOUT_SANIYE * 1000})
    except Exception as e:
        log("critical", f"Bağlantı kurulamadı: {e}")
        log_q.put(("done", ([], 0, [])))
        return

    CIKTI = os.path.join(klasor, cikti_adi)

    if retry_dosyalar is not None:
        islenmemis_pdf = [d for d in retry_dosyalar if not d.lower().endswith(".xml")]
        islenmemis_xml = [d for d in retry_dosyalar if d.lower().endswith(".xml")]
        toplam = len(islenmemis_pdf) + len(islenmemis_xml)
        mevcut_satirlar, _ = mevcut_verileri_oku(CIKTI)
        if toplam == 0:
            log("info", "Yeniden denenecek dosya bulunamadı.")
            log_q.put(("done", ([], 0, [])))
            return
        log("info", f"{toplam} fatura yeniden denenecek.")
    else:
        pdf_dosyalar = sorted(glob.glob(os.path.join(klasor, "*.pdf")))
        xml_only = [x for x in sorted(glob.glob(os.path.join(klasor, "*.xml")))
                    if not os.path.exists(os.path.splitext(x)[0] + ".pdf")]

        if not pdf_dosyalar and not xml_only:
            log("critical", "Klasörde işlenecek PDF veya XML dosyası bulunamadı.")
            log_q.put(("done", ([], 0, [])))
            return

        mevcut_satirlar, islenenmis = mevcut_verileri_oku(CIKTI)
        if islenenmis:
            log("info", f"Mevcut Excel'de {len(islenenmis)} fatura var, sadece yeniler işlenecek.")

        islenmemis_pdf = [d for d in pdf_dosyalar if os.path.basename(d).lower() not in islenenmis]
        islenmemis_xml = [x for x in xml_only if os.path.basename(x).lower() not in islenenmis]
        toplam = len(islenmemis_pdf) + len(islenmemis_xml)

        if toplam == 0:
            log("info", "Tüm faturalar zaten işlenmiş, yeni fatura yok.")
            log_q.put(("done", ([], 0, [])))
            return

        log("info", f"{toplam} fatura işlenecek ({len(islenmemis_pdf)} PDF, {len(islenmemis_xml)} XML-only).")

    log_q.put(("progress", (0, toplam)))

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

    def atla(dosya_adi, sebep):
        nonlocal siradaki
        siradaki += 1
        log_q.put(("progress", (siradaki, toplam)))
        log("skip", f"⚠  {dosya_adi}: {sebep}")
        atlanmis.append((dosya_adi, sebep))

    # ── PDF dosyaları (paralel) ────────────────────────────────────────
    api_hata = threading.Event()

    def pdf_gorevi(dosya):
        if stop_event.is_set() or api_hata.is_set():
            return None
        dosya_adi = os.path.basename(dosya)
        xml_yolu  = os.path.splitext(dosya)[0] + ".xml"
        if os.path.exists(xml_yolu):
            log("info", f"→  {dosya_adi[:60]}")
            try:
                return ("ok", xml_den_veri_cek(xml_yolu, dosya))
            except XMLHatasi as e:
                return ("atla", (dosya_adi, str(e)))
            except Exception as e:
                return ("atla", (dosya_adi, f"Beklenmedik hata — {type(e).__name__}: {e}"))
        else:
            if not pdf_gecerli_mi(dosya):
                return ("atla", (dosya_adi, "PDF açılamadı. Dosya bozuk veya şifreli olabilir."))
            log("info", f"→  {dosya_adi[:60]}")
            try:
                return ("ok", pdf_den_veri_cek(dosya, client, log_q, stop_event, zoom))
            except APIKeyHatasi as e:
                api_hata.set()
                return ("critical", str(e))
            except (PDFHatasi, InternetHatasi, ModelHatasi) as e:
                return ("atla", (dosya_adi, str(e)))
            except Exception as e:
                return ("atla", (dosya_adi, f"Beklenmedik hata — {type(e).__name__}: {e}"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_dosya = {executor.submit(pdf_gorevi, d): d for d in islenmemis_pdf}
        bekleyen = set(future_to_dosya.keys())

        while bekleyen:
            if stop_event.is_set():
                for f in bekleyen:
                    f.cancel()
                log("info", "İşlem kullanıcı tarafından durduruldu.")
                break

            biten, bekleyen = concurrent.futures.wait(
                bekleyen, timeout=1,
                return_when=concurrent.futures.FIRST_COMPLETED)

            for future in biten:
                result = future.result()
                if result is None:
                    continue
                tip, veri = result
                if tip == "ok":
                    islendi(veri)
                elif tip == "atla":
                    atla(*veri)
                elif tip == "critical":
                    log("critical", str(veri))
                    for f in bekleyen:
                        f.cancel()
                    log_q.put(("done", (atlanmis, yeni, uyari_listesi)))
                    return

    # ── XML-only dosyalar ──────────────────────────────────────────────
    for xml_dosya in islenmemis_xml:
        if stop_event.is_set():
            log("info", "İşlem kullanıcı tarafından durduruldu.")
            break

        dosya_adi = os.path.basename(xml_dosya)
        log("info", f"→  {dosya_adi[:60]}")
        try:
            islendi(xml_den_veri_cek(xml_dosya, None))
        except XMLHatasi as e:
            atla(dosya_adi, str(e))
        except Exception as e:
            atla(dosya_adi, f"Beklenmedik hata — {type(e).__name__}: {e}")

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


# ─── GUI ──────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk):
        self.root       = root
        self.root.title(f"Fatura Ayıklama  v{VERSION}")
        self.root.resizable(False, False)

        try:
            _icon = tk.PhotoImage(data=_ICON_B64)
            self.root.iconphoto(True, _icon)
        except Exception:
            pass

        # Tema tercihini _build_ui'den ÖNCE yükle
        load_dotenv(dotenv_path=ENV_DOSYASI)
        _tema_uygula(os.environ.get("TEMA", "dark") == "dark")

        self.stop_event = threading.Event()
        self.log_queue  = queue.Queue()
        self.klasor_var = tk.StringVar()
        self.api_var    = tk.StringVar()
        self.cikti_var  = tk.StringVar(value="faturalar")
        self.zoom_var   = tk.StringVar(value="1.5")

        self.son_cikti  = ""
        self._baslangic = 0.0
        self._atlanmis  = []
        self._uyarilar  = []
        self._klasor    = ""

        self._build_ui()
        self._load_api_key()
        self.root.after(100, self._poll_queue)

    # ── Arayüz ────────────────────────────────────────────────────────
    def _build_ui(self):
        self.root.configure(bg=BG)

        # Başlık
        tk.Label(self.root, text="Fatura Ayıklama", font=("Arial", 15, "bold"),
                 bg=MANTLE, fg=BLUE).pack(fill="x", ipady=10)

        # Ayarlar çerçevesi
        frame = tk.LabelFrame(self.root, text=" Ayarlar ", font=("Arial", 9),
                               bg=MANTLE, fg=SUBTEXT, padx=10, pady=8)
        frame.pack(fill="x", padx=14, pady=(12, 4))

        # Klasör seçimi
        tk.Label(frame, text="Klasör:", width=9, anchor="w",
                 bg=MANTLE, fg=TEXT, font=("Arial", 9)).grid(row=0, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.klasor_var, state="readonly",
                 width=36, font=("Arial", 9),
                 bg=SURFACE, fg=SUBTEXT, readonlybackground=SURFACE,
                 relief="flat", insertbackground=TEXT,
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        tk.Button(frame, text="Seç…", command=self._select_folder,
                  bg=SURFACE, fg=BLUE, relief="flat", padx=8,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=TEXT,
                  ).grid(row=0, column=2, padx=(0, 4))
        tk.Button(frame, text="🔑 API Key", command=self._change_key,
                  bg=SURFACE, fg=SUBTEXT, relief="flat", padx=8,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=TEXT,
                  ).grid(row=0, column=3)

        self.key_status = tk.Label(frame, text="", font=("Arial", 8),
                                   bg=MANTLE, fg=GREEN)
        self.key_status.grid(row=0, column=4, padx=(6, 0), sticky="w")

        # Dosya adı + Geçmiş
        tk.Label(frame, text="Dosya Adı:", width=9, anchor="w",
                 bg=MANTLE, fg=TEXT, font=("Arial", 9)).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Entry(frame, textvariable=self.cikti_var, width=28, font=("Arial", 9),
                 bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief="flat",
                 ).grid(row=1, column=1, sticky="w", padx=(0, 4), pady=(6, 0))
        tk.Label(frame, text=".xlsx", bg=MANTLE, fg=SUBTEXT,
                 font=("Arial", 9)).grid(row=1, column=2, sticky="w", pady=(6, 0))
        tk.Button(frame, text="📋 Geçmiş", command=self._gecmis_goster,
                  bg=SURFACE, fg=SUBTEXT, relief="flat", padx=8,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=TEXT,
                  ).grid(row=1, column=3, pady=(6, 0))

        self.btn_kalite = tk.Button(
            frame, text="⚙ Kalite: Normal", command=self._kalite_popup,
            bg=SURFACE, fg=SUBTEXT, relief="flat", padx=8,
            cursor="hand2", font=("Arial", 9),
            activebackground=SURFACE, activeforeground=TEXT)
        self.btn_kalite.grid(row=1, column=4, padx=(8, 0), pady=(6, 0))

        tema_ikonu = "🌙" if BG == _KARANLIK["BG"] else "☀"
        self.btn_tema = tk.Button(
            frame, text=tema_ikonu, command=self._tema_degistir,
            bg=SURFACE, fg=SUBTEXT, relief="flat", padx=8,
            cursor="hand2", font=("Arial", 10),
            activebackground=SURFACE, activeforeground=TEXT)
        self.btn_tema.grid(row=1, column=5, padx=(4, 0), pady=(6, 0))

        frame.columnconfigure(1, weight=1)

        # Butonlar
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=14, pady=6)

        self.btn_start = tk.Button(btn_frame, text="▶  Başlat", command=self._start,
                                   width=12, bg=SURFACE, fg=GREEN,
                                   font=("Arial", 9), relief="flat",
                                   cursor="hand2", pady=3,
                                   activebackground=SURFACE, activeforeground=GREEN)
        self.btn_start.pack(side="left")

        self.btn_excel = tk.Button(btn_frame, text="📂 Excel'i Aç",
                                   command=self._excel_ac, bg=SURFACE, fg=BLUE,
                                   relief="flat", padx=8, pady=3, cursor="hand2",
                                   font=("Arial", 9), state="disabled",
                                   activebackground=SURFACE, activeforeground=TEXT)
        self.btn_excel.pack(side="left", padx=(8, 0))

        self.btn_stop = tk.Button(btn_frame, text="■  Durdur", command=self._stop,
                                  width=12, bg=SURFACE, fg=RED,
                                  font=("Arial", 9), relief="flat",
                                  cursor="hand2", pady=3, state="disabled",
                                  activebackground=SURFACE, activeforeground=RED)
        self.btn_stop.pack(side="right")

        self.btn_retry = tk.Button(btn_frame, text="↺ Yeniden Dene",
                                   command=self._yeniden_dene, bg=SURFACE, fg=RED,
                                   relief="flat", padx=8, pady=3, cursor="hand2",
                                   font=("Arial", 9), state="disabled",
                                   activebackground=SURFACE, activeforeground=TEXT)
        self.btn_retry.pack(side="right", padx=(0, 8))

        self.btn_uyari = tk.Button(btn_frame, text="⚠ Uyarılar",
                                   command=self._uyari_popup, bg=SURFACE, fg="#f9e2af",
                                   relief="flat", padx=8, pady=3, cursor="hand2",
                                   font=("Arial", 9), state="disabled",
                                   activebackground=SURFACE, activeforeground="#f9e2af")
        self.btn_uyari.pack(side="right", padx=(0, 8))

        # İlerleme
        prog_frame = tk.Frame(self.root, bg=BG)
        prog_frame.pack(fill="x", padx=14, pady=(0, 2))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("dark.Horizontal.TProgressbar",
                        troughcolor=SURFACE, background=BLUE, borderwidth=0)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                        style="dark.Horizontal.TProgressbar")
        self.progress.pack(fill="x", expand=True)

        self.prog_label = tk.Label(self.root, text="", bg=BG, fg=TEXT,
                                   font=("Arial", 8), anchor="e")
        self.prog_label.pack(fill="x", padx=14, pady=(0, 4))

        # Log alanı
        log_frame = tk.LabelFrame(self.root, text=" İşlem Günlüğü ",
                                   font=("Arial", 9), bg=BG, fg=SUBTEXT, padx=4, pady=4)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self.log_text = tk.Text(log_frame, height=18, width=80,
                                font=("Consolas", 9), bg=BG, fg=TEXT,
                                relief="flat", state="disabled", wrap="word")
        self.log_text.bind("<MouseWheel>",
            lambda e: self.log_text.yview_scroll(-1 * (e.delta // 120), "units"))
        self.log_text.pack(fill="both", expand=True)

        self.log_text.tag_config("ok",       foreground="#a6e3a1")
        self.log_text.tag_config("skip",     foreground="#fab387")
        self.log_text.tag_config("critical", foreground="#f38ba8", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("warn",     foreground="#f9e2af")
        self.log_text.tag_config("info",     foreground="#89b4fa")
        self.log_text.tag_config("done_ok",  foreground="#a6e3a1", font=("Consolas", 9, "bold"))

        self.root.geometry("620x640")

    # ── API Key yönetimi ───────────────────────────────────────────────
    def _load_api_key(self):
        load_dotenv(dotenv_path=ENV_DOSYASI)
        key = os.environ.get("GEMINI_API_KEY", "")
        if key:
            self.api_var.set(key)
            self.key_status.config(text="✓ key yüklendi")
        else:
            self.root.after(300, self._ask_api_key_popup)

    def _ask_api_key_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("API Key Gerekli")
        popup.configure(bg=MANTLE)
        popup.resizable(False, False)
        popup.grab_set()
        popup.transient(self.root)

        tk.Label(popup, text="Google AI API Key",
                 font=("Arial", 11, "bold"), bg=MANTLE, fg=BLUE
                 ).pack(pady=(16, 4), padx=20)
        tk.Label(popup,
                 text="Devam etmek için API key girin.\n(aistudio.google.com → Get API Key)",
                 font=("Arial", 9), bg=MANTLE, fg=SUBTEXT, justify="center"
                 ).pack(pady=(0, 10), padx=20)

        entry_var = tk.StringVar()
        entry = tk.Entry(popup, textvariable=entry_var, show="●",
                         width=40, font=("Consolas", 9),
                         bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief="flat")
        entry.pack(padx=20, pady=(0, 4))
        entry.focus_set()

        show_var = tk.BooleanVar(value=False)
        def toggle_show():
            entry.config(show="" if show_var.get() else "●")
        tk.Checkbutton(popup, text="Göster", variable=show_var, command=toggle_show,
                       bg=MANTLE, fg=SUBTEXT, selectcolor=SURFACE,
                       activebackground=MANTLE, font=("Arial", 8)
                       ).pack(anchor="w", padx=20)

        status = tk.Label(popup, text="", font=("Arial", 8), bg=MANTLE, fg=RED)
        status.pack(pady=(2, 0))

        def kaydet():
            key = entry_var.get().strip()
            if not key:
                status.config(text="Key boş olamaz.")
                return
            set_key(str(ENV_DOSYASI), "GEMINI_API_KEY", key)
            self.api_var.set(key)
            self.key_status.config(text="✓ key yüklendi")
            popup.destroy()

        tk.Button(popup, text="Kaydet ve Devam Et", command=kaydet,
                  bg=SURFACE, fg=GREEN, relief="flat", padx=12, pady=4,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=GREEN,
                  ).pack(pady=(8, 16))

        popup.bind("<Return>", lambda e: kaydet())
        self._center_popup(popup)

    def _change_key(self):
        self._ask_api_key_popup()

    def _center_popup(self, popup: tk.Toplevel):
        """popup'ı ana pencereye göre ortalar."""
        self.root.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width() // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        popup.geometry(f"+{rx - pw//2}+{ry - ph//2}")

    def _tema_degistir(self):
        """Temayı değiştir, arayüzü yeniden oluştur, tercihi kaydet."""
        zoom = self.zoom_var.get()
        api_yuklendi = "✓" in self.key_status.cget("text")

        yeni_karanlik = (BG == _AYDINLIK["BG"])  # şu an açıksa karanlığa, karanlıksa açığa
        _tema_uygula(yeni_karanlik)
        try:
            set_key(str(ENV_DOSYASI), "TEMA", "dark" if yeni_karanlik else "light")
        except Exception:
            pass

        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()

        _ZOOM_ADI = {"1.0": "Hızlı", "1.5": "Normal", "2.0": "Yüksek", "3.0": "Maksimum"}
        self.btn_kalite.config(text=f"⚙ Kalite: {_ZOOM_ADI.get(zoom, 'Normal')}")
        if api_yuklendi:
            self.key_status.config(text="✓ key yüklendi")

    def _select_folder(self):
        klasor = filedialog.askdirectory(title="Fatura Klasörünü Seçin")
        if klasor:
            self.klasor_var.set(klasor)

    def _uyari_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Veri Uyarıları")
        popup.configure(bg=MANTLE)
        popup.resizable(False, False)
        popup.transient(self.root)

        toplam_u = sum(len(u) for _, u in self._uyarilar)
        tk.Label(popup, text=f"Veri Uyarıları  ({toplam_u} uyarı, {len(self._uyarilar)} fatura)",
                 font=("Arial", 11, "bold"), bg=MANTLE, fg="#f9e2af"
                 ).pack(pady=(14, 6), padx=20)
        tk.Label(popup,
                 text="Bu uyarılar işlemi durdurmaz; yalnızca kontrol edilmesi\n"
                      "önerilen alanları gösterir.",
                 font=("Arial", 8), bg=MANTLE, fg=SUBTEXT, justify="center"
                 ).pack(pady=(0, 8), padx=20)

        # Kaydırılabilir liste
        container = tk.Frame(popup, bg=MANTLE)
        container.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        canvas = tk.Canvas(container, bg=MANTLE, highlightthickness=0,
                           width=420, height=min(320, 60 + toplam_u * 20 + len(self._uyarilar) * 24))
        sb = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        ic = tk.Frame(canvas, bg=MANTLE)
        canvas.create_window((0, 0), window=ic, anchor="nw")

        for dosya_adi, uyarilar in self._uyarilar:
            # Dosya başlığı
            tk.Label(ic, text=f"📄 {dosya_adi}",
                     font=("Arial", 9, "bold"), bg=MANTLE, fg=TEXT,
                     anchor="w").pack(fill="x", pady=(8, 1), padx=4)
            for u in uyarilar:
                tk.Label(ic, text=f"    ⚠  {u}",
                         font=("Arial", 8), bg=MANTLE, fg="#f9e2af",
                         anchor="w").pack(fill="x", padx=4)

        ic.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.bind("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        tk.Button(popup, text="Kapat", command=popup.destroy,
                  bg=SURFACE, fg=TEXT, relief="flat", padx=16, pady=4,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=TEXT,
                  ).pack(pady=(0, 14))
        self._center_popup(popup)

    def _kalite_popup(self):
        _SECENEKLER = [
            ("1.0", "Hızlı",    "En hızlı işlem. Düşük çözünürlük — küçük\nmetinler okunmayabilir."),
            ("1.5", "Normal",   "Hız ve doğruluk dengesi. Çoğu fatura\niçin yeterli. (Önerilen)"),
            ("2.0", "Yüksek",   "Daha yüksek doğruluk. İşlem süresi\nyaklaşık 2× artar."),
            ("3.0", "Maksimum", "En yüksek doğruluk. İşlem süresi\n~4× artar; büyük PDF'lerde yavaş."),
        ]

        popup = tk.Toplevel(self.root)
        popup.title("Kalite Seçimi")
        popup.configure(bg=MANTLE)
        popup.resizable(False, False)
        popup.grab_set()
        popup.transient(self.root)

        tk.Label(popup, text="PDF Okuma Kalitesi",
                 font=("Arial", 11, "bold"), bg=MANTLE, fg=BLUE
                 ).pack(pady=(16, 4), padx=20)
        tk.Label(popup,
                 text="Daha yüksek kalite daha doğru sonuç verir,\nancak işlem süresi artar.",
                 font=("Arial", 9), bg=MANTLE, fg=SUBTEXT, justify="center"
                 ).pack(pady=(0, 12), padx=20)

        secim_var = tk.StringVar(value=self.zoom_var.get())

        for deger, ad, aciklama in _SECENEKLER:
            satir = tk.Frame(popup, bg=MANTLE)
            satir.pack(fill="x", padx=20, pady=3)

            rb = tk.Radiobutton(
                satir, variable=secim_var, value=deger,
                text=f"{ad}  ({deger}×)",
                font=("Arial", 9, "bold"),
                bg=MANTLE, fg=TEXT,
                selectcolor=SURFACE,
                activebackground=MANTLE, activeforeground=TEXT,
                cursor="hand2",
            )
            rb.pack(anchor="w")

            tk.Label(satir, text=aciklama,
                     font=("Arial", 8), bg=MANTLE, fg=SUBTEXT,
                     justify="left", padx=24
                     ).pack(anchor="w")

        def uygula():
            secilen = secim_var.get()
            self.zoom_var.set(secilen)
            ad = next(a for d, a, _ in _SECENEKLER if d == secilen)
            self.btn_kalite.config(text=f"⚙ Kalite: {ad}")
            popup.destroy()

        tk.Button(popup, text="Uygula", command=uygula,
                  bg=SURFACE, fg=GREEN, relief="flat", padx=16, pady=4,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=GREEN,
                  ).pack(pady=(12, 16))

        popup.bind("<Return>", lambda e: uygula())
        self._center_popup(popup)

    # ── İşlem kontrolü ────────────────────────────────────────────────
    def _start(self):
        api_key = self.api_var.get().strip()
        klasor  = self.klasor_var.get().strip()
        if not api_key:
            self._ask_api_key_popup()
            return
        if not klasor:
            messagebox.showerror("Hata", "Lütfen bir klasör seçin.")
            return

        cikti_adi = (self.cikti_var.get().strip() or "faturalar") + ".xlsx"
        self.son_cikti  = os.path.join(klasor, cikti_adi)
        self._klasor    = klasor
        self._baslangic = time.time()

        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_excel.config(state="disabled")
        self.btn_retry.config(state="disabled", text="↺ Yeniden Dene")
        self.btn_uyari.config(state="disabled", text="⚠ Uyarılar")
        self.btn_tema.config(state="disabled")
        self._uyarilar = []
        self.progress["value"] = 0
        self.prog_label.config(text="")
        self._clear_log()

        threading.Thread(
            target=worker,
            args=(api_key, klasor, cikti_adi, self.log_queue, self.stop_event),
            kwargs={"zoom": float(self.zoom_var.get())},
            daemon=True
        ).start()

    def _stop(self):
        self.stop_event.set()
        self.btn_stop.config(state="disabled")
        self._log("warn", "⚠ Durdurma isteği gönderildi, mevcut fatura tamamlanıyor…")

    def _excel_ac(self):
        if self.son_cikti and os.path.exists(self.son_cikti):
            os.startfile(self.son_cikti)

    def _yeniden_dene(self):
        if not self._atlanmis or not self._klasor:
            return
        retry_yollar = [os.path.join(self._klasor, ad) for ad, _ in self._atlanmis]
        cikti_adi = (self.cikti_var.get().strip() or "faturalar") + ".xlsx"
        self._baslangic = time.time()
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_retry.config(state="disabled")
        self.btn_excel.config(state="disabled")
        self.btn_uyari.config(state="disabled", text="⚠ Uyarılar")
        self.btn_tema.config(state="disabled")
        self._uyarilar = []
        self.progress["value"] = 0
        self.prog_label.config(text="")
        self._clear_log()
        threading.Thread(
            target=worker,
            args=(self.api_var.get().strip(), self._klasor, cikti_adi,
                  self.log_queue, self.stop_event),
            kwargs={"retry_dosyalar": retry_yollar, "zoom": float(self.zoom_var.get())},
            daemon=True
        ).start()

    # ── Geçmiş ────────────────────────────────────────────────────────
    def _gecmis_kaydet(self, islenen: int, atlanan: int):
        kayit = {
            "tarih":   time.strftime("%Y-%m-%d %H:%M"),
            "klasor":  os.path.basename(self._klasor) or self._klasor,
            "dosya":   self.cikti_var.get().strip() or "faturalar",
            "islenen": islenen,
            "atlanan": atlanan,
            "sure_dk": round((time.time() - self._baslangic) / 60, 1),
        }
        try:
            gecmis = json.loads(GECMIS_DOSYASI.read_text("utf-8")) \
                     if GECMIS_DOSYASI.exists() else []
        except Exception:
            gecmis = []
        gecmis.append(kayit)
        try:
            GECMIS_DOSYASI.write_text(
                json.dumps(gecmis[-100:], ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass

    def _gecmis_goster(self):
        try:
            gecmis = json.loads(GECMIS_DOSYASI.read_text("utf-8")) \
                     if GECMIS_DOSYASI.exists() else []
        except Exception:
            gecmis = []

        popup = tk.Toplevel(self.root)
        popup.title("İşlem Geçmişi")
        popup.configure(bg=MANTLE)
        popup.resizable(False, False)
        popup.transient(self.root)

        tk.Label(popup, text="İşlem Geçmişi", font=("Arial", 11, "bold"),
                 bg=MANTLE, fg=BLUE).pack(pady=(14, 8), padx=20)

        if not gecmis:
            tk.Label(popup, text="Henüz kayıt yok.", bg=MANTLE, fg=SUBTEXT,
                     font=("Arial", 9)).pack(pady=(0, 16), padx=20)
        else:
            tablo = tk.Frame(popup, bg=MANTLE)
            tablo.pack(padx=16, pady=(0, 14))

            basliklar = ["Tarih", "Klasör", "Dosya", "İşlenen", "Atlanan", "Süre"]
            for ci, b in enumerate(basliklar):
                tk.Label(tablo, text=b, bg=SURFACE, fg=BLUE, font=("Arial", 8, "bold"),
                         padx=6, pady=3, relief="flat", anchor="w"
                         ).grid(row=0, column=ci, sticky="ew", padx=1, pady=1)

            for ri, k in enumerate(reversed(gecmis[-20:]), 1):
                degerler = [
                    k.get("tarih", ""),
                    k.get("klasor", "")[:22],
                    k.get("dosya", ""),
                    str(k.get("islenen", 0)),
                    str(k.get("atlanan", 0)),
                    f"{k.get('sure_dk', 0)}dk",
                ]
                zebra = SURFACE if ri % 2 == 0 else MANTLE
                for ci, d in enumerate(degerler):
                    tk.Label(tablo, text=d, bg=zebra, fg=TEXT, font=("Arial", 8),
                             padx=6, pady=2, anchor="w"
                             ).grid(row=ri, column=ci, sticky="ew", padx=1, pady=0)

        tk.Button(popup, text="Kapat", command=popup.destroy,
                  bg=SURFACE, fg=TEXT, relief="flat", padx=16, pady=4,
                  cursor="hand2", font=("Arial", 9),
                  activebackground=SURFACE, activeforeground=TEXT,
                  ).pack(pady=(8, 14))
        self._center_popup(popup)

    # ── Queue polling ──────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                tag, data = self.log_queue.get_nowait()

                if tag == "progress":
                    current, total = data
                    self.progress["maximum"] = total
                    self.progress["value"]   = current
                    gecen = time.time() - self._baslangic
                    if current > 0 and gecen > 2:
                        hiz = current / gecen
                        kalan_sn = (total - current) / hiz
                        if kalan_sn < 60:
                            eta = f"~{int(kalan_sn)}s"
                        else:
                            eta = f"~{int(kalan_sn / 60)}dk"
                        self.prog_label.config(text=f"{current}/{total}  {eta} kaldı")
                    else:
                        self.prog_label.config(text=f"{current}/{total}")

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

                elif tag == "critical":
                    self._log("critical", f"🛑 {data}")
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.btn_tema.config(state="normal")
                    messagebox.showerror("Kritik Hata", data)

                else:
                    self._log(tag, data)

        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ── Log yardımcıları ───────────────────────────────────────────────
    def _log(self, tag: str, mesaj: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", mesaj + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
