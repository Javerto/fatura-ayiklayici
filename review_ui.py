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

        # önizleme durumu
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

        # Sabit başlangıç boyutu: içerik (büyük PDF render'ı) pencereyi
        # ekrandan taşıracak şekilde büyütemesin; kullanıcı boyutlandırabilsin.
        ekran_w = self.win.winfo_screenwidth()
        ekran_h = self.win.winfo_screenheight()
        w = min(1180, ekran_w - 80)
        h = min(720, ekran_h - 120)
        x = (ekran_w - w) // 2
        y = max(20, (ekran_h - h) // 2 - 20)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.minsize(880, 620)

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
                                 show="headings", height=6)
        for k, b, w in [("fatura_no", "Fatura No", 160), ("sirket_adi", "Şirket", 210),
                        ("tutar", "Tutar", 90), ("kaynak", "Kaynak", 70),
                        ("uyari", "⚠", 40)]:
            self.tree.heading(k, text=b)
            self.tree.column(k, width=w, anchor="w")
        self.tree.tag_configure("uyari", background=p.get("WARNING_BG", "#3a3a2a"),
                                foreground=p.get("WARNING_FG", "#f9e2af"))
        self.tree.tag_configure("haric", foreground=p["OVERLAY"])
        sb = ttk.Scrollbar(tablo_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._satir_secildi)

        # Alt buton çubuğu — orta bölümden ÖNCE, side="bottom" ile pack edilir;
        # pencere küçülse bile butonlar hiçbir zaman ekran dışında kalmaz.
        alt = tk.Frame(self.win, bg=p["BG"])
        alt.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
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

    # ── Önizleme (gömülü PDF render) ──
    def _onizleme_kur(self):
        p = self.p
        # Kontrol çubuğu önce, side="bottom" ile: canvas büyüse de kaybolmaz.
        kontrol = tk.Frame(self.onizleme_frame, bg=p["MANTLE"])
        kontrol.pack(side="bottom", fill="x", pady=(6, 0))
        govde = tk.Frame(self.onizleme_frame, bg=p["MANTLE"])
        govde.pack(fill="both", expand=True)
        govde.rowconfigure(0, weight=1)
        govde.columnconfigure(0, weight=1)
        self.onizleme_canvas = tk.Canvas(govde, bg=p["MANTLE"],
                                         highlightthickness=0)
        vsb = ttk.Scrollbar(govde, orient="vertical",
                            command=self.onizleme_canvas.yview)
        hsb = ttk.Scrollbar(govde, orient="horizontal",
                            command=self.onizleme_canvas.xview)
        self.onizleme_canvas.configure(yscrollcommand=vsb.set,
                                       xscrollcommand=hsb.set)
        self.onizleme_canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.onizleme_canvas.bind(
            "<MouseWheel>",
            lambda e: self.onizleme_canvas.yview_scroll(
                -1 if e.delta > 0 else 1, "units"))
        self._onizleme_mesaj("Önizleme yok")
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
                                    cursor="hand2", state="disabled")
        self.dis_ac_btn.pack(side="right", padx=2)

    def _onizleme_mesaj(self, metin):
        c = self.onizleme_canvas
        c.delete("all")
        cw = max(c.winfo_width(), 200)
        c.create_text(cw // 2, 40, text=metin, fill=self.p["SUBTEXT"],
                      font=("Arial", 9))
        c.configure(scrollregion=(0, 0, 0, 0))
        self._tk_img = None

    def _onizleme_yukle(self, yol):
        self._pdf_yol = yol
        self.sayfa = 0
        if self._pdf_doc is not None:
            self._pdf_doc.close()
            self._pdf_doc = None
        if not yol or not str(yol).lower().endswith(".pdf") or not os.path.exists(yol):
            self._onizleme_mesaj("Önizleme yok (XML / PDF bulunamadı)")
            self.sayfa_label.config(text="")
            self.dis_ac_btn.config(state="disabled")
            return
        try:
            self._pdf_doc = fitz.open(yol)
        except Exception:
            self._onizleme_mesaj("Önizleme yüklenemedi")
            self.sayfa_label.config(text="")
            self.dis_ac_btn.config(state="disabled")
            return
        self.dis_ac_btn.config(state="normal")
        self._sigdir_zoom()
        self._sayfayi_ciz()

    def _sigdir_zoom(self):
        """İlk yüklemede zoom'u panel genişliğine sığacak şekilde ayarlar."""
        if self._pdf_doc is None or self._pdf_doc.page_count <= 0:
            return
        self.win.update_idletasks()
        cw = self.onizleme_canvas.winfo_width()
        if cw <= 50:
            return
        try:
            sayfa_w = self._pdf_doc[0].rect.width or 595
        except Exception:
            return
        self.zoom = max(0.5, min(3.0, (cw - 8) / sayfa_w))

    def _sayfayi_ciz(self):
        if self._pdf_doc is None:
            return
        n = self._pdf_doc.page_count
        if n <= 0:
            self._onizleme_mesaj("Önizleme yüklenemedi")
            self.sayfa_label.config(text="")
            return
        self.sayfa = max(0, min(self.sayfa, n - 1))
        try:
            pix = self._pdf_doc[self.sayfa].get_pixmap(
                matrix=fitz.Matrix(self.zoom, self.zoom))
            png_b64 = base64.b64encode(pix.tobytes("png")).decode()
            self._tk_img = tk.PhotoImage(data=png_b64)
            c = self.onizleme_canvas
            c.delete("all")
            c.create_image(0, 0, anchor="nw", image=self._tk_img)
            c.configure(scrollregion=(0, 0, pix.width, pix.height))
            c.xview_moveto(0)
            c.yview_moveto(0)
        except Exception:
            self._onizleme_mesaj("Önizleme yüklenemedi")
        self.sayfa_label.config(text=f"sayfa {self.sayfa + 1} / {n}")

    def _zoom_degistir(self, d):
        self.zoom = max(0.5, min(3.0, self.zoom + d))
        self._sayfayi_ciz()

    def _sayfa_degistir(self, d):
        if self._pdf_doc is None:
            return
        self.sayfa += d
        self._sayfayi_ciz()

    def _disarida_ac(self):
        if self._pdf_yol and os.path.exists(self._pdf_yol):
            try:
                os.startfile(self._pdf_yol)
            except OSError as e:
                messagebox.showerror("Hata", f"Dosya açılamadı:\n{e}",
                                     parent=self.win)

    # ── Onay / İptal ──
    def _onayla(self):
        kalan = sum(1 for i in range(len(self.yeni))
                    if i not in self.haric and self.uyari[i])
        if kalan and not messagebox.askyesno(
                "Uyarılar var",
                f"{kalan} faturada hâlâ uyarı var. Yine de Excel'e yazılsın mı?",
                parent=self.win):
            return
        nihai = nihai_satirlar(self.mevcut, self.yeni, self.haric)
        guncel_uyarilar = [
            (os.path.basename(self.yeni[i].get("dosya_yolu") or "bilinmiyor"),
             self.uyari[i])
            for i in range(len(self.yeni)) if i not in self.haric and self.uyari[i]]
        if self.on_confirm(nihai, guncel_uyarilar):
            if self._pdf_doc is not None:
                self._pdf_doc.close()
                self._pdf_doc = None
            self.win.destroy()

    def _iptal(self):
        if messagebox.askyesno(
                "İptal",
                "Çıkarılan veriler ve düzeltmeler kaydedilmeyecek. Emin misiniz?",
                parent=self.win):
            if self._pdf_doc is not None:
                self._pdf_doc.close()
                self._pdf_doc = None
            self.win.destroy()
            self.on_cancel()
