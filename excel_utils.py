"""
Excel okuma ve yazma işlemleri.
"""

import os
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from extraction import ExcelHatasi

SUTUN = {
    "ft_formul":            1,
    "fatura_no":            2,
    "fatura_tarihi":        3,
    "sira_no":              4,
    "tanim":                5,
    "toplam_miktar":        6,
    "vergiler_dahil_tutar": 7,
    "para_birimi":          8,
    "kdv_haric_tutar":      9,
    "vergi_tutari":         10,
    "sirket_adi":           11,
    "vkn":                  12,
    "vergi_dairesi":        13,
    "dosya":                14,
    "dosya_yolu_gizli":     15,
}


def excel_guvenli(deger):
    """Excel'de izin verilmeyen karakterleri temizler."""
    if not isinstance(deger, str):
        return deger
    return ILLEGAL_CHARACTERS_RE.sub("", deger)


def dosya_url(dosya_yolu: str) -> str:
    """Dosya yolunu geçerli file:// URL'e çevirir. UNC path'leri de destekler."""
    p = dosya_yolu.replace("\\", "/")
    if p.startswith("//"):
        # UNC path: \\sunucu\paylasim → file://sunucu/paylasim/...
        return "file:" + p
    else:
        # Yerel path: C:\klasor → file:///C:/klasor/...
        return "file:///" + p


def url_dosya(url: str) -> str:
    """file:// URL'inden dosya yoluna çevirir."""
    if url.startswith("file:////"):
        # Bozuk UNC (eski format): file:////sunucu → \\sunucu
        return url[8:].replace("/", "\\")
    elif url.startswith("file://") and not url.startswith("file:///"):
        # Doğru UNC: file://sunucu → \\sunucu
        return "\\\\" + url[7:].replace("/", "\\")
    else:
        # Yerel: file:///C:/... → C:\...
        return url.replace("file:///", "").replace("/", "\\")


def mevcut_verileri_oku(cikti: str) -> tuple[list[dict], set[str]]:
    """Mevcut Excel'deki faturaları ve işlenmiş dosya adlarını okur."""
    if not os.path.exists(cikti):
        return [], set()
    try:
        wb = load_workbook(cikti, data_only=True)
    except Exception:
        return [], set()

    ws = wb.active
    satirlar, islenenmis = [], set()

    for row in ws.iter_rows(min_row=2, max_col=SUTUN["dosya_yolu_gizli"]):
        b_val = row[SUTUN["fatura_no"] - 1].value
        if not b_val or str(b_val).strip().upper() == "TOPLAM":
            continue
        s = {
            "fatura_no":            row[SUTUN["fatura_no"] - 1].value,
            "fatura_tarihi":        row[SUTUN["fatura_tarihi"] - 1].value,
            "sira_no":              row[SUTUN["sira_no"] - 1].value,
            "tanim":                row[SUTUN["tanim"] - 1].value,
            "toplam_miktar":        row[SUTUN["toplam_miktar"] - 1].value,
            "vergiler_dahil_tutar": row[SUTUN["vergiler_dahil_tutar"] - 1].value,
            "para_birimi":          row[SUTUN["para_birimi"] - 1].value,
            "kdv_haric_tutar":      row[SUTUN["kdv_haric_tutar"] - 1].value,
            "sirket_adi":           row[SUTUN["sirket_adi"] - 1].value,
            "vkn":                  row[SUTUN["vkn"] - 1].value,
            "vergi_dairesi":        row[SUTUN["vergi_dairesi"] - 1].value,
        }
        n_cell     = row[SUTUN["dosya"] - 1]
        gizli_cell = row[SUTUN["dosya_yolu_gizli"] - 1]
        dosya_yolu = ""
        # O sütunu: tam dosya yolu — hyperlink bozulsa bile güvenilir kaynak
        gizli_val = str(gizli_cell.value).strip() if gizli_cell.value else ""
        if gizli_val.lower().endswith((".pdf", ".xml")):
            dosya_yolu = gizli_val
            islenenmis.add(os.path.basename(gizli_val).lower())
        else:
            # Geriye dönük uyumluluk: eski format — hyperlink'ten oku
            if n_cell.hyperlink and n_cell.hyperlink.target:
                dosya_yolu = url_dosya(n_cell.hyperlink.target)
                islenenmis.add(os.path.basename(dosya_yolu).lower())
            else:
                n_val = str(n_cell.value).strip() if n_cell.value else ""
                if n_val.lower().endswith((".pdf", ".xml")):
                    islenenmis.add(n_val.lower())
        s["dosya_yolu"] = dosya_yolu
        satirlar.append(s)

    wb.close()
    return satirlar, islenenmis


def excel_olustur(satirlar: list, cikti: str):
    """Fatura listesinden biçimlendirilmiş Excel dosyası oluşturur."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Faturalar"

    baslik_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    baslik_fill = PatternFill("solid", start_color="2F5496")
    orta        = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ince        = Side(style="thin", color="CCCCCC")
    kenar       = Border(left=ince, right=ince, top=ince, bottom=ince)
    f10         = Font(name="Arial", size=10)
    flink       = Font(name="Arial", size=10, color="0563C1", underline="single")
    fbold       = Font(name="Arial", bold=True, size=10)
    num_fmt     = "#,##0.00"
    zebra_fill  = PatternFill("solid", start_color="EEF2F9")
    toplam_fill = PatternFill("solid", start_color="D9E1F2")

    sutunlar = [
        ("F+T", 39), ("Fatura No", 22), ("Fatura Tarihi", 13), ("Sıra No", 7),
        ("Tanım", 37), ("Toplam Adet", 8), ("Vergiler Dahil Tutar", 16),
        ("Para Birimi", 7), ("KDV Hariç Tutar", 16), ("Vergi Tutarı", 16),
        ("Şirket Adı", 31), ("VKN", 14), ("Vergi Dairesi", 22), ("Dosya", 12),
    ]
    for col, (baslik, _) in enumerate(sutunlar, 1):
        c = ws.cell(row=1, column=col, value=baslik)
        c.font, c.fill, c.alignment, c.border = baslik_font, baslik_fill, orta, kenar
    ws.row_dimensions[1].height = 30

    gizli_harf = get_column_letter(SUTUN["dosya_yolu_gizli"])
    fn_hrf  = get_column_letter(SUTUN["fatura_no"])
    ft_hrf  = get_column_letter(SUTUN["fatura_tarihi"])
    vdt_hrf = get_column_letter(SUTUN["vergiler_dahil_tutar"])
    kdv_hrf = get_column_letter(SUTUN["kdv_haric_tutar"])
    tm_hrf  = get_column_letter(SUTUN["toplam_miktar"])
    vt_hrf  = get_column_letter(SUTUN["vergi_tutari"])

    for ri, s in enumerate(satirlar, 2):
        zebra = zebra_fill if ri % 2 == 0 else None
        ws.cell(row=ri, column=SUTUN["ft_formul"],
                value=f"=+{fn_hrf}{ri}&{ft_hrf}{ri}")

        veri_map = {
            SUTUN["fatura_no"]:            s.get("fatura_no", ""),
            SUTUN["fatura_tarihi"]:        s.get("fatura_tarihi", ""),
            SUTUN["sira_no"]:              s.get("sira_no"),
            SUTUN["tanim"]:                s.get("tanim", ""),
            SUTUN["toplam_miktar"]:        s.get("toplam_miktar"),
            SUTUN["vergiler_dahil_tutar"]: s.get("vergiler_dahil_tutar"),
            SUTUN["para_birimi"]:          s.get("para_birimi", "TL"),
            SUTUN["kdv_haric_tutar"]:      s.get("kdv_haric_tutar"),
            SUTUN["sirket_adi"]:           s.get("sirket_adi", ""),
            SUTUN["vkn"]:                  s.get("vkn", ""),
            SUTUN["vergi_dairesi"]:        s.get("vergi_dairesi", ""),
        }
        for col, val in veri_map.items():
            c = ws.cell(row=ri, column=col, value=excel_guvenli(val))
            c.font, c.border = f10, kenar
            c.alignment = Alignment(vertical="center")
            if col in (SUTUN["vergiler_dahil_tutar"], SUTUN["kdv_haric_tutar"]) and isinstance(val, (int, float)):
                c.number_format = num_fmt
            if col == SUTUN["fatura_tarihi"] and hasattr(val, "strftime"):
                c.number_format = "DD.MM.YYYY"
            if zebra:
                c.fill = zebra

        jc = ws.cell(row=ri, column=SUTUN["vergi_tutari"],
                     value=f"=+{vdt_hrf}{ri}-{kdv_hrf}{ri}")
        jc.font, jc.border, jc.number_format = f10, kenar, num_fmt
        jc.alignment = Alignment(vertical="center")
        if zebra:
            jc.fill = zebra

        ac = ws.cell(row=ri, column=SUTUN["ft_formul"])
        ac.font, ac.border = f10, kenar
        if zebra:
            ac.fill = zebra

        lh = ws.cell(row=ri, column=SUTUN["dosya"])
        dosya_yolu = s.get("dosya_yolu", "")
        if dosya_yolu.lower().endswith(".pdf"):
            lh.value = (f'=HYPERLINK("file:///"&SUBSTITUTE({gizli_harf}{ri},'
                        f'"\\\\","/"),"Faturayı Aç")')
            lh.font = flink
        elif dosya_yolu.lower().endswith(".xml"):
            lh.value = "XML"
            lh.font = f10
        else:
            lh.font = f10
        lh.border = kenar
        lh.alignment = Alignment(horizontal="center", vertical="center")
        if zebra:
            lh.fill = zebra

        # Gizli sütun: tam dosya yolu — hyperlink bozulsa bile kod buradan okur
        gc = ws.cell(row=ri, column=SUTUN["dosya_yolu_gizli"], value=dosya_yolu)
        gc.font = Font(name="Arial", size=1, color="FFFFFF")  # beyaz, 1pt — görünmez
        gc.alignment = Alignment(horizontal="center", vertical="center")

    for col, (_, w) in enumerate(sutunlar, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.column_dimensions[gizli_harf].hidden = True

    sr = len(satirlar) + 2
    ws.cell(row=sr, column=SUTUN["fatura_no"], value="TOPLAM").font = fbold
    for col, fml in [
        (SUTUN["toplam_miktar"],        f"=SUM({tm_hrf}2:{tm_hrf}{sr-1})"),
        (SUTUN["vergiler_dahil_tutar"], f"=SUM({vdt_hrf}2:{vdt_hrf}{sr-1})"),
        (SUTUN["kdv_haric_tutar"],      f"=SUM({kdv_hrf}2:{kdv_hrf}{sr-1})"),
        (SUTUN["vergi_tutari"],         f"=SUM({vt_hrf}2:{vt_hrf}{sr-1})"),
    ]:
        c = ws.cell(row=sr, column=col, value=fml)
        c.font = fbold
        if col in (SUTUN["vergiler_dahil_tutar"], SUTUN["kdv_haric_tutar"], SUTUN["vergi_tutari"]):
            c.number_format = num_fmt
    for col in range(1, 15):
        c = ws.cell(row=sr, column=col)
        c.border, c.fill = kenar, toplam_fill

    try:
        wb.save(cikti)
    except PermissionError:
        raise ExcelHatasi(
            f"'{os.path.basename(cikti)}' kaydedilemedi.\n"
            "Dosya Excel'de açık olabilir. Kapatıp tekrar deneyin.")
