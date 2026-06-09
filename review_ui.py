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
        self.tree.tag_configure("uyari", background=p.get("WARNING_BG", "#3a3a2a"),
                                foreground=p.get("WARNING_FG", "#f9e2af"))
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
                f"{kalan} faturada hâlâ uyarı var. Yine de Excel'e yazılsın mı?",
                parent=self.win):
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
                "Çıkarılan veriler ve düzeltmeler kaydedilmeyecek. Emin misiniz?",
                parent=self.win):
            self.win.destroy()
            self.on_cancel()
