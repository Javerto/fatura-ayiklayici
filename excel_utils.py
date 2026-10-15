"""
Excel okuma ve yazma işlemleri.
"""

import os
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from hatalar import ExcelHatasi
import sema as _sema
# Gömülü şemasız eski dosyaların düzeni tohumunkidir (kademe 2/3); yazılan ve
# okunan alan listesi ise verilen şemadan gelir.
from fatura import ALANLAR as TOHUM_ALANLARI, SUTUN as TOHUM_SUTUN
from fatura import kaynak as fatura_kaynak   # yerel `kaynak` adlarıyla çakışmasın
from ozet import ozet_hesapla

# Gizli sayfa: dosyanın hangi düzenle yazıldığını (anahtar → sütun) taşır, böylece
# okuma koddaki sütun numaralarına değil dosyanın kendisine güvenir.
SEMA_SAYFASI = "_Sema"


def _bos(alan):
    """Satırda alan yoksa hücreye yazılacak değer: sayıda boş hücre, metinde ''."""
    if alan.anahtar == "para_birimi":
        return "TL"
    return None if alan.tip == "sayi" else ""


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


def mevcut_verileri_oku(cikti: str, sema=None) -> tuple[list[dict], set[str]]:
    """Mevcut Excel'deki faturaları ve işlenmiş dosya adlarını okur.

    Okunan alanlar `sema`nınkilerdir (pasifler dahil — sütunları korunur);
    dosyada olmayan alan None gelir.
    """
    veri_alanlari = (sema or _sema.VARSAYILAN).alanlar
    if not os.path.exists(cikti):
        return [], set()
    try:
        wb = load_workbook(cikti, data_only=True)
    except Exception as e:
        # Okunamayan dosyayı "kayıt yok" sayarsak bir sonraki onay onu
        # sıfırdan yazar ve birikmiş tüm geçmiş gider. Okuyamıyorsak durmalıyız.
        raise ExcelHatasi(
            f"'{os.path.basename(cikti)}' okunamadı: {e}\n"
            "Dosya bozuk veya başka bir programda açık olabilir. "
            "Üzerine yazmamak için işlem durduruldu.") from e

    # wb.active, dosyanın en son hangi sekmede kaydedildiğine bakar; kullanıcı
    # Özet sekmesinde bırakıp kaydettiyse oranın hücreleri fatura sanılır.
    ws = wb["Faturalar"] if "Faturalar" in wb.sheetnames else wb.worksheets[0]
    satirlar, islenenmis = [], set()

    sutun = _sutun_haritasi(wb, ws)
    for row in ws.iter_rows(min_row=2, max_col=max(sutun.values())):
        def hucre(anahtar):
            # Gömülü şemada olmayan alan bu dosyada hiç yazılmamış demektir.
            return row[sutun[anahtar] - 1] if anahtar in sutun else None

        def deger(anahtar):
            c = hucre(anahtar)
            return c.value if c is not None else None

        b_val = deger("fatura_no")
        if not b_val or str(b_val).strip().upper() == "TOPLAM":
            continue
        kaynak_val = deger("kaynak")
        s = {a.anahtar: deger(a.anahtar) for a in veri_alanlari}
        s["_teknik_bilgi"] = str(kaynak_val).strip() if kaynak_val else ""
        n_cell = hucre("dosya")
        dosya_yolu = ""
        # Gizli sütun: tam dosya yolu — hyperlink bozulsa bile güvenilir kaynak
        gizli_val = deger("dosya_yolu_gizli")
        gizli_val = str(gizli_val).strip() if gizli_val else ""
        if gizli_val.lower().endswith((".pdf", ".xml")):
            dosya_yolu = gizli_val
            islenenmis.add(os.path.basename(gizli_val).lower())
        elif n_cell is not None:
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


def _sutun_haritasi(wb, ws) -> dict[str, int]:
    """Dosyanın hangi sütunda neyi tuttuğu (anahtar → sütun), üç kademede.

    1. Gömülü şema sayfası (`SEMA_SAYFASI`) — dosyanın kendi beyanı. Beyan
       başlık da taşıyorsa ve bir başlık başlık satırında BAŞKA bir sütunda
       duruyorsa (kullanıcı sütun sildi/ekledi) numaralar güvenilmez: o
       beyanın başlıklarıyla kademe 2'ye düşülür.
    2. Başlık satırı — "Fatura No" başlığı tanınan dosya; başlıksız sütunlar
       (gizli yol) soldaki en yakın bulunan komşunun kaymasıyla bulunur.
    3. Bugünkü sabit sütun numaraları — en eski dosyalar.
    """
    satir1 = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
    beyan = _gomulu_sema(wb)
    if beyan:
        # Yalnızca yeniden adlandırılan başlık (bulunamayan) kaymayı göstermez:
        # o durumda numaralar hâlâ doğru, başlığa düşmek o alanı kaybederdi.
        kaymis = any(b in satir1 and satir1[b] != s for s, b, _ in beyan.values() if b)
        if not kaymis:
            return {k: s for k, (s, _, _) in beyan.items()}
        harita = _basliktan(satir1, {k: (s, b) for k, (s, b, _) in beyan.items()})
        if "fatura_no" in harita:
            return harita
    # ponytail: bozuk/boş şema sayfası → alt kademelere düş, hata verme

    # Başlıklar tohumunkiler: kullanıcı etiketi değiştirse de eski dosya tanınır.
    harita = _basliktan(satir1, {a.anahtar: (a.sutun, a.baslik) for a in TOHUM_ALANLARI})
    return harita if "fatura_no" in harita else dict(TOHUM_SUTUN)


def _basliktan(satir1: dict, beyan: dict) -> dict[str, int]:
    """Başlık satırından anahtar → sütun. `beyan`: {anahtar: (sütun, başlık)}.

    Başlığı bulunamayan alan haritaya girmez (silinmiş; sabit numarası artık
    başka bir alanın verisini tutuyor olabilir). Başlıksız sütunun yeri, soldaki
    en yakın bulunan komşunun kaymasından ve aradaki bulunamayan (silinmiş)
    başlıklı sütun sayısından çıkarılır.
    """
    harita = {k: satir1[b] for k, (_, b) in beyan.items() if b and b in satir1}
    for k, (s, b) in beyan.items():
        if b:
            continue
        solda = [(beyan[j][0], harita[j]) for j in harita if beyan[j][0] < s]
        if not solda:
            harita[k] = s
            continue
        eski, yeni = max(solda)
        silinen = sum(1 for j, (t, bb) in beyan.items()
                      if bb and eski < t < s and j not in harita)
        harita[k] = yeni + (s - eski) - silinen
    return harita


def _gomulu_sema(wb) -> dict[str, tuple] | None:
    """`_Sema` beyanı: {anahtar: (sütun, başlık, tip)}; yoksa ya da bozuksa None.

    Eski (iki sütunlu) sayfalarda başlık ve tip None'dır. Tek ayrıştırma
    noktası: okuma kademesi, uyuşmazlık uyarısı ve arşiv şeması aynı
    satırları aynı denetimle görsün.
    """
    if SEMA_SAYFASI not in wb.sheetnames:
        return None
    beyan = {}
    for r in wb[SEMA_SAYFASI].iter_rows(min_row=2, values_only=True):
        k, s, b, t = (tuple(r) + (None,) * 4)[:4]
        if k and isinstance(s, int) and s > 0:
            beyan[str(k)] = (s, str(b) if b else None, t if t in _sema.TIPLER else None)
    return beyan if "fatura_no" in beyan else None


def _arsiv_beyani(cikti: str, ornek=False):
    """(gömülü şema, {sütun: başlık}, {sütun: ilk dolu değer}) — dosya
    yok/eski/okunamıyorsa None. Örnek değerler yalnızca `ornek=True` ise okunur
    (tüm sayfayı gezer)."""
    if not os.path.exists(cikti):
        return None
    try:
        wb = load_workbook(cikti, read_only=True)
        try:
            gomulu = _gomulu_sema(wb)
            if gomulu is None:
                return None
            ws = wb["Faturalar"] if "Faturalar" in wb.sheetnames else wb.worksheets[0]
            satirlar = ws.iter_rows(values_only=True)
            basliklar = dict(enumerate(next(satirlar, ()), 1))
            ornekler = {}
            for r in (satirlar if ornek else ()):
                for i, v in enumerate(r, 1):
                    if v is not None:
                        ornekler.setdefault(i, v)
        finally:
            wb.close()
    except Exception:
        return None   # ponytail: bilgi amaçlı; okuma hatasını mevcut_verileri_oku yakalar
    return gomulu, basliklar, ornekler


def _tip_cikar(deger):
    """Tip taşımayan eski `_Sema` için: hücre değerinden tarih/sayı, yoksa None."""
    if hasattr(deger, "strftime"):
        return "tarih"
    if isinstance(deger, (int, float)) and not isinstance(deger, bool):
        return "sayi"
    return None


def arsiv_semasi(cikti: str, sema=None):
    """`sema` + arşivin `_Sema`sında olup `sema`da hiç olmayan alanlar (pasif).

    Bu alanlar okunur ve kendi başlık ve tipleriyle geri yazılır: başka bir
    şemayla yazılmış arşiv onaylanınca sütunları sessizce silinmesin, tarih
    sütunu biçimini kaybetmesin. Sütunu aktif şemada başka bir alana
    verilmişse en sağdaki dolu sütunun hemen sağına taşınır (ezilmez).
    """
    sema = sema or _sema.VARSAYILAN
    beyan = _arsiv_beyani(cikti, ornek=True)
    if not beyan:
        return sema
    gomulu, basliklar, ornekler = beyan
    dolu = set(sema.sutun.values())
    ekler = []
    for k, (s, b, t) in sorted(gomulu.items(), key=lambda x: x[1][0]):
        if k in sema.sutun:
            continue
        baslik = str(b or basliklar.get(s) or k)
        tip = t or _tip_cikar(ornekler.get(s))
        if s in dolu:
            s = max(dolu) + 1
        dolu.add(s)
        ekler.append(_sema.Alan(k, s, baslik, _sema.VARSAYILAN_GENISLIK,
                                etiket=baslik, tip=tip, aktif=False))
    return _sema.Sema(sema.alanlar + ekler) if ekler else sema


def sema_farki(cikti: str, sema=None) -> dict | None:
    """Arşivin gömülü şeması `sema`dan farklıysa hangi alanların ayrıştığı.

    `{"arsivde_fazla": [başlık...], "yeni": [etiket...]}`; dosya yoksa, gömülü
    şeması yoksa (eski dosya) ya da şemalar aynıysa None. Koşu düzeyinde bir
    bilgidir, işlemi durdurmaz — okunamayan dosya da None döner. Arşivde fazla
    olan sütunlar korunur (`arsiv_semasi`); bu yüzden o kısım kalıcı bir bilgidir.
    """
    sema = sema or _sema.VARSAYILAN
    beyan = _arsiv_beyani(cikti)
    if not beyan:
        return None
    gomulu, basliklar, _ = beyan
    aktif = {a.anahtar: a for a in sema.tum_alanlar}
    # Arşive özgü alanın etiketi şemada yok; kullanıcı anahtarı değil başlığı tanır.
    fazla = [str(b or basliklar.get(s) or k) for k, (s, b, _) in gomulu.items()
             if k not in aktif]
    yeni = [a.baslik or a.anahtar for k, a in aktif.items() if k not in gomulu]
    return {"arsivde_fazla": fazla, "yeni": yeni} if fazla or yeni else None


def excel_olustur(satirlar: list, cikti: str, sema=None):
    """Fatura listesinden biçimlendirilmiş Excel dosyası oluşturur.

    Sütunlar, başlıklar ve genişlikler `sema`dan gelir (verilmezse varsayılan).
    """
    sema = sema or _sema.VARSAYILAN
    sutun = sema.sutun
    sutun_bilgisi = sorted((a for a in sema.tum_alanlar if a.baslik),
                           key=lambda a: a.sutun)
    tarih_sutunlari = {a.sutun for a in sema.alanlar if a.tip == "tarih"}
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

    for a in sutun_bilgisi:
        c = ws.cell(row=1, column=a.sutun, value=a.baslik)
        c.font, c.fill, c.alignment, c.border = baslik_font, baslik_fill, orta, kenar
    ws.row_dimensions[1].height = 30

    gizli_harf = get_column_letter(sutun["dosya_yolu_gizli"])
    fn_hrf  = get_column_letter(sutun["fatura_no"])
    ft_hrf  = get_column_letter(sutun["fatura_tarihi"])
    vdt_hrf = get_column_letter(sutun["vergiler_dahil_tutar"])
    kdv_hrf = get_column_letter(sutun["kdv_haric_tutar"])
    tm_hrf  = get_column_letter(sutun["toplam_miktar"])
    vt_hrf  = get_column_letter(sutun["vergi_tutari"])
    kht_aktif = "kdv_haric_tutar" in sema.aktif_anahtarlar

    for ri, s in enumerate(satirlar, 2):
        zebra = zebra_fill if ri % 2 == 0 else None
        ws.cell(row=ri, column=sutun["ft_formul"],
                value=f"=+{fn_hrf}{ri}&{ft_hrf}{ri}")

        veri_map = {a.sutun: s.get(a.anahtar, _bos(a)) for a in sema.alanlar}
        for col, val in veri_map.items():
            c = ws.cell(row=ri, column=col, value=excel_guvenli(val))
            c.font, c.border = f10, kenar
            c.alignment = Alignment(vertical="center")
            if col in (sutun["vergiler_dahil_tutar"], sutun["kdv_haric_tutar"]) and isinstance(val, (int, float)):
                c.number_format = num_fmt
            if col in tarih_sutunlari and hasattr(val, "strftime"):
                c.number_format = "DD.MM.YYYY"
            if zebra:
                c.fill = zebra

        # kdv_haric_tutar pasifse yeni satırda yoktur; formül vergiyi dahil
        # tutar kadar gösterirdi. Arşivde değeri olan eski satırda anlamlı, kalır.
        vergi_var = kht_aktif or s.get("kdv_haric_tutar") is not None
        jc = ws.cell(row=ri, column=sutun["vergi_tutari"],
                     value=f"=+{vdt_hrf}{ri}-{kdv_hrf}{ri}" if vergi_var else None)
        jc.font, jc.border, jc.number_format = f10, kenar, num_fmt
        jc.alignment = Alignment(vertical="center")
        if zebra:
            jc.fill = zebra

        ac = ws.cell(row=ri, column=sutun["ft_formul"])
        ac.font, ac.border = f10, kenar
        if zebra:
            ac.fill = zebra

        lh = ws.cell(row=ri, column=sutun["dosya"])
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
        gc = ws.cell(row=ri, column=sutun["dosya_yolu_gizli"], value=dosya_yolu)
        gc.font = Font(name="Arial", size=1, color="FFFFFF")  # beyaz, 1pt — görünmez
        gc.alignment = Alignment(horizontal="center", vertical="center")

        # Kaynak sütunu: Dijital / OCR (PDF) veya XML
        kc = ws.cell(row=ri, column=sutun["kaynak"], value=fatura_kaynak(s))
        kc.font, kc.border = f10, kenar
        kc.alignment = Alignment(horizontal="center", vertical="center")
        if zebra:
            kc.fill = zebra

    for a in sutun_bilgisi:
        ws.column_dimensions[get_column_letter(a.sutun)].width = a.genislik
    ws.column_dimensions[gizli_harf].hidden = True

    sr = len(satirlar) + 2
    ws.cell(row=sr, column=sutun["fatura_no"], value="TOPLAM").font = fbold
    for col, fml in [
        (sutun["toplam_miktar"],        f"=SUM({tm_hrf}2:{tm_hrf}{sr-1})"),
        (sutun["vergiler_dahil_tutar"], f"=SUM({vdt_hrf}2:{vdt_hrf}{sr-1})"),
        (sutun["kdv_haric_tutar"],      f"=SUM({kdv_hrf}2:{kdv_hrf}{sr-1})"),
        (sutun["vergi_tutari"],         f"=SUM({vt_hrf}2:{vt_hrf}{sr-1})"),
    ]:
        c = ws.cell(row=sr, column=col, value=fml)
        c.font = fbold
        if col in (sutun["vergiler_dahil_tutar"], sutun["kdv_haric_tutar"], sutun["vergi_tutari"]):
            c.number_format = num_fmt
    for col in range(1, max(sutun.values()) + 1):
        if col == sutun["dosya_yolu_gizli"]:
            continue
        c = ws.cell(row=sr, column=col)
        c.border, c.fill = kenar, toplam_fill

    _ozet_sayfasi_yaz(wb, satirlar)
    _sema_sayfasi_yaz(wb, sema)

    _guvenli_kaydet(wb, cikti)


def _sema_sayfasi_yaz(wb, sema):
    # Pasif alanlar da yazılır: yazılmazsa kademe 1 onları None okur ve
    # arşivdeki verileri bir sonraki onayda düşer.
    # Başlık: elle silinen/eklenen sütunu yakalamak için (`_sutun_haritasi`);
    # tip: arşive özgü alan geri yazılırken biçimini korusun (`arsiv_semasi`).
    ws = wb.create_sheet(SEMA_SAYFASI)
    ws.append(["anahtar", "sutun", "baslik", "tip"])
    for a in sorted(sema.tum_alanlar, key=lambda a: a.sutun):
        ws.append([a.anahtar, a.sutun, a.baslik, a.tip])
    ws.sheet_state = "hidden"


def _guvenli_kaydet(wb, cikti: str):
    """Önce geçici dosyaya yazar, sonra yerine taşır.

    Doğrudan `wb.save(cikti)` hedefi anında sıfırlıyor; yazma yarıda kesilirse
    (disk dolu, ağ sürücüsü koptu, süreç öldürüldü) geriye yarım bir dosya
    kalıyor ve birikmiş tüm fatura geçmişi gidiyordu. `os.replace` Windows'ta
    atomiktir: ya eski dosya ya yenisi durur, arası yok.
    """
    gecici = cikti + ".tmp"
    try:
        wb.save(gecici)
        os.replace(gecici, cikti)
    except PermissionError as e:
        _sil(gecici)
        raise ExcelHatasi(
            f"'{os.path.basename(cikti)}' kaydedilemedi.\n"
            "Dosya Excel'de açık olabilir. Kapatıp tekrar deneyin.") from e
    except OSError as e:
        _sil(gecici)
        raise ExcelHatasi(
            f"'{os.path.basename(cikti)}' kaydedilemedi: {e}\n"
            "Mevcut dosyaya dokunulmadı.") from e


def _sil(yol: str):
    try:
        os.remove(yol)
    except OSError:
        pass


def _ozet_sayfasi_yaz(wb, satirlar: list):
    """Çalışma kitabına 'Özet' sayfası ekler (genel/aylık/şirket blokları)."""
    o = ozet_hesapla(satirlar)
    ws = wb.create_sheet("Özet")

    baslik_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    baslik_fill = PatternFill("solid", start_color="2F5496")
    fbold = Font(name="Arial", bold=True, size=10)
    f10 = Font(name="Arial", size=10)
    num_fmt = "#,##0.00"

    r = 1

    def blok_baslik(metin):
        nonlocal r
        for col in range(1, 5):
            c = ws.cell(row=r, column=col)
            c.fill = baslik_fill
        c = ws.cell(row=r, column=1, value=metin)
        c.font, c.fill = baslik_font, baslik_fill
        r += 1

    def deger_satiri(etiket, deger, sayi=False):
        nonlocal r
        ws.cell(row=r, column=1, value=etiket).font = f10
        c = ws.cell(row=r, column=2, value=deger)
        c.font = f10
        if sayi:
            c.number_format = num_fmt
        r += 1

    # ── GENEL ──
    blok_baslik("GENEL")
    deger_satiri("Fatura Adedi", o["genel"]["adet"])
    for pb in sorted(o["genel"]["tutar"]):
        deger_satiri(f"Toplam Tutar ({pb})", o["genel"]["tutar"][pb], sayi=True)
    for pb in sorted(o["genel"]["kdv"]):
        deger_satiri(f"Toplam KDV ({pb})", o["genel"]["kdv"][pb], sayi=True)
    for kaynak in sorted(o["genel"]["kaynak"]):
        deger_satiri(f"Kaynak: {kaynak}", o["genel"]["kaynak"][kaynak])
    r += 1

    def kirilim_tablosu(baslik, ilk_kolon_adi, kayitlar):
        """kayitlar: [(ad, {"adet", "tutar": {pb: toplam}})]"""
        nonlocal r
        blok_baslik(baslik)
        for col, h in enumerate(
                [ilk_kolon_adi, "Adet", "Para Birimi", "Toplam Tutar"], 1):
            ws.cell(row=r, column=col, value=h).font = fbold
        r += 1
        for ad, v in kayitlar:
            pb_listesi = sorted(v["tutar"]) or [None]
            for i, pb in enumerate(pb_listesi):
                if i == 0:
                    ws.cell(row=r, column=1, value=ad).font = f10
                    ws.cell(row=r, column=2, value=v["adet"]).font = f10
                if pb is not None:
                    ws.cell(row=r, column=3, value=pb).font = f10
                    c = ws.cell(row=r, column=4, value=v["tutar"][pb])
                    c.font, c.number_format = f10, num_fmt
                r += 1
        r += 1

    kirilim_tablosu("AYLIK", "Ay", o["aylik"])
    kirilim_tablosu("ŞİRKET", "Şirket", o["sirket"])

    for col, w in [(1, 34), (2, 12), (3, 12), (4, 16)]:
        ws.column_dimensions[get_column_letter(col)].width = w
