"""Şema: hangi alanların faturadan çıkarılacağının tek gerçek kaynağı.

Alan seti bir veri dosyasıdır (`alanlar.json`); model promptu, Excel sütunları,
gözden geçirme formu ve öğrenen düzeltme alanları bundan **türer**. Dosya ilk
açılışta gömülü tohumdan (`TOHUM`) yazılır, sonrası hep dosyadan okunur.

`Sema` bir değerdir: ilgili fonksiyonlar `sema=None` parametresi alır, verilmezse
`VARSAYILAN` (tohumun kendisi, dosyasız) kullanılır. Dosyayı yalnızca `Api`
okur (`Api(kok=...)` konumunu belirler) ve şemayı açıkça aşağı geçirir; böylece
testler gerçek `alanlar.json`'a hiç dokunmaz.
"""
import json
import os
from typing import NamedTuple

SURUM = 1
TIPLER = ("metin", "tarih", "sayi")
CEKIRDEK = ("fatura_no", "fatura_tarihi", "sirket_adi", "vkn",
            "vergiler_dahil_tutar", "para_birimi")
VARSAYILAN_GENISLIK = 16


class Alan(NamedTuple):
    """Bir alanın Excel, form, öğrenme ve prompt tarafındaki karşılığı."""
    anahtar: str
    sutun: int                  # Excel sütun numarası (1 tabanlı)
    baslik: str | None = None   # Excel başlığı; None → başlıksız sütun
    genislik: int | None = None
    etiket: str | None = None   # form etiketi; None → formda düzenlenmez
    tip: str | None = None      # "metin" | "tarih" | "sayi"
    ogrenilir: bool = False     # VKN bazlı firma-sabit alan mı
    aciklama: str = ""          # modele giden alan açıklaması
    cekirdek: bool = False
    aktif: bool = True
    zorunlu: bool = False


# Formda yeri olmayan, Excel'e özel sütunlar. Şema dosyasında değil kodda
# dururlar: formülleri ve gizli yol sütununu kod üretir. Numaraları ayrılmıştır.
SISTEM_ALANLARI = [
    Alan("ft_formul",        1,  "F+T",          39),   # =fatura_no&tarih
    Alan("vergi_tutari",     10, "Vergi Tutarı", 16),   # =dahil-hariç
    Alan("dosya",            14, "Dosya",        12),   # hyperlink
    Alan("dosya_yolu_gizli", 15),                       # gizli tam yol
    Alan("kaynak",           16, "Kaynak",       9),
]


def _t(anahtar, etiket, tip, sutun, genislik, aciklama, ogrenilir=False):
    return {"anahtar": anahtar, "etiket": etiket, "tip": tip, "sutun": sutun,
            "genislik": genislik, "cekirdek": anahtar in CEKIRDEK, "aktif": True,
            "zorunlu": anahtar in CEKIRDEK, "ogrenilir": ogrenilir,
            "aciklama": aciklama}


# Gömülü tohum. Sıra = gözden geçirme formundaki ve prompttaki sıra. Açıklamalar
# eski elle yazılmış `PROMPT_SABLON`'dan birebir taşındı. `sutun` numaraları eski
# Excel dosyalarının düzenidir — asla yeniden numaralandırma.
TOHUM = {"surum": SURUM, "alanlar": [
    _t("fatura_no", "Fatura No", "metin", 2, 22,
       "fatura numarası — Türk e-fatura standardı: 3 karakter (büyük harf veya rakam) + 4 haneli yıl + 9 haneli sıra, toplam 16 karakter (örn: GIB2024000000001). Fazladan sıfır EKLEME."),
    _t("fatura_tarihi", "Fatura Tarihi", "tarih", 3, 13,
       "GG.AA.YYYY formatında tarih"),
    _t("sirket_adi", "Şirket Adı", "metin", 11, 31,
       "faturayı kesen SATICI şirketin adı. Faturada iki şirket varsa ALICI değil SATICI olanı yaz.",
       ogrenilir=True),
    _t("vkn", "VKN", "metin", 12, 14,
       "SATICI şirketin VKN'i (10-11 haneli). Faturada birden fazla VKN varsa SATICI olana ait olanı yaz."),
    _t("vergi_dairesi", "Vergi Dairesi", "metin", 13, 22,
       "satıcı şirketin vergi dairesi adı", ogrenilir=True),
    _t("tanim", "Tanım", "metin", 5, 37,
       "ilk kalem ya da ana hizmetin açıklaması"),
    _t("toplam_miktar", "Toplam Adet", "sayi", 6, 8,
       "toplam adet/miktar (sadece sayı, örnek: 7 veya 14.5)"),
    _t("kdv_haric_tutar", "KDV Hariç Tutar", "sayi", 9, 16,
       "KDV hariç Mal/Hizmet Toplam Tutarı, TL cinsinden sayı. EUR ve TL varsa TL ver. Yoksa null"),
    _t("vergiler_dahil_tutar", "Vergiler Dahil Tutar", "sayi", 7, 16,
       'Vergiler Dahil Toplam Tutar, TL cinsinden sayı. "Ödenecek Tutar(TL)" veya "Vergiler Dahil Toplam Tutar(TL)" satırını bul. EUR/TL karışıksa TL ver'),
    _t("para_birimi", "Para Birimi", "metin", 8, 7,
       "TL ya da yalnızca döviz varsa EUR veya USD"),
    _t("sira_no", "Sıra No", "sayi", 4, 7,
       'yatırım teşvik belgesinin kaçıncı sıra nosu — SADECE şu kalıplardan birinde geçiyorsa al: "X sırasında KDV istisnası", "Yerli Liste X sırasında", "Sıra No: X kapsamında","Liste Y-x sıra numarasına istinaden". Diğer no alanlarını ASLA alma. Yoksa null'),
]}


class Sema:
    """Bir alan seti. Türetilen her görünüm (Excel, form, prompt) buradan çıkar."""

    def __init__(self, alanlar: list[Alan]):
        self.alanlar = list(alanlar)          # veri alanları, form sırasıyla
        self.tum_alanlar = self.alanlar + SISTEM_ALANLARI
        self.sutun = {a.anahtar: a.sutun for a in self.tum_alanlar}

    def __eq__(self, diger):
        return isinstance(diger, Sema) and self.alanlar == diger.alanlar

    @property
    def duzenlenebilir(self) -> list[tuple[str, str, str]]:
        """Form alanları (anahtar, etiket, tip) — sıra formdaki sıradır."""
        return [(a.anahtar, a.etiket, a.tip) for a in self.alanlar]

    @property
    def ogrenilen(self) -> list[str]:
        """VKN bazlı öğrenilen, firma-sabit alanlar."""
        return [a.anahtar for a in self.alanlar if a.ogrenilir]

    @property
    def tip_haritasi(self) -> dict[str, str]:
        return {a.anahtar: a.tip for a in self.alanlar}

    def json(self) -> dict:
        """Dosyaya yazılacak biçim."""
        return {"surum": SURUM, "alanlar": [
            {"anahtar": a.anahtar, "etiket": a.etiket, "tip": a.tip,
             "sutun": a.sutun, "genislik": a.genislik, "cekirdek": a.cekirdek,
             "aktif": a.aktif, "zorunlu": a.zorunlu, "ogrenilir": a.ogrenilir,
             "aciklama": a.aciklama}
            for a in self.alanlar]}


_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _slug(etiket: str, kullanilan: set) -> str:
    """Etiketten anahtar: "Sipariş No" → "siparis_no"; çakışırsa sona sayı."""
    kok = "".join(c if c.isalnum() else "_"
                  for c in etiket.translate(_TR).lower())
    kok = "_".join(p for p in kok.split("_") if p) or "alan"
    aday, n = kok, 2
    while aday in kullanilan:
        aday, n = f"{kok}_{n}", n + 1
    return aday


def _coz(ham) -> Sema:
    """Ham JSON'dan Sema; biçim bozuksa ValueError.

    Onarılanlar (dosyaya geri yazılır): eksik `anahtar` etiketten, eksik `sutun`
    sona atanır; dosyadan silinmiş tohum alanı geri eklenir; tohum alanlarının
    sütunu ve tipi tohumdakidir (kod onlara adıyla dayanıyor).
    """
    if (not isinstance(ham, dict) or ham.get("surum") != SURUM
            or not isinstance(ham.get("alanlar"), list)):
        raise ValueError("şema biçimi tanınmadı")
    tohum = {d["anahtar"]: d for d in TOHUM["alanlar"]}
    ayrilmis = {a.sutun for a in SISTEM_ALANLARI} | {d["sutun"] for d in tohum.values()}

    girdiler = []
    for d in ham["alanlar"]:
        if not isinstance(d, dict):
            raise ValueError("alan bir nesne değil")
        d = dict(d)
        anahtar = d.get("anahtar")
        if anahtar in tohum:
            d["sutun"], d["tip"] = tohum[anahtar]["sutun"], tohum[anahtar]["tip"]
        etiket = d.get("etiket")
        if not isinstance(etiket, str) or not etiket.strip():
            raise ValueError("boş etiket")
        if d.get("tip") not in TIPLER:
            raise ValueError(f"bilinmeyen tip: {d.get('tip')!r}")
        sutun = d.get("sutun")
        if anahtar not in tohum and sutun is not None and (
                type(sutun) is not int or sutun < 1 or sutun in ayrilmis):
            raise ValueError(f"geçersiz sütun: {sutun!r}")
        girdiler.append(d)

    # Anahtarlar önce dosyada yazılı olanlar arasından, sonra eksikler türetilir:
    # türetilen bir anahtar asla dosyadaki bir anahtarı gölgelememeli.
    yazili = [d["anahtar"] for d in girdiler if d.get("anahtar")]
    if len(yazili) != len(set(yazili)) or not all(isinstance(k, str) for k in yazili):
        raise ValueError("yinelenen/geçersiz anahtar")
    kullanilan = set(tohum) | set(yazili)
    for d in girdiler:
        if not d.get("anahtar"):
            d["anahtar"] = _slug(d["etiket"], kullanilan)
            kullanilan.add(d["anahtar"])
    gorulen = [d["anahtar"] for d in girdiler]

    girdiler += [dict(t) for k, t in tohum.items() if k not in gorulen]
    sutunlar = [d["sutun"] for d in girdiler if d.get("sutun") is not None]
    if len(sutunlar) != len(set(sutunlar)):
        raise ValueError("yinelenen sütun")
    sonraki = max(sutunlar + list(ayrilmis)) + 1
    for d in girdiler:
        if d.get("sutun") is None:
            d["sutun"], sonraki = sonraki, sonraki + 1

    return Sema([Alan(
        anahtar=d["anahtar"], sutun=d["sutun"], baslik=d["etiket"].strip(),
        genislik=d.get("genislik") or VARSAYILAN_GENISLIK,
        etiket=d["etiket"].strip(), tip=d["tip"],
        ogrenilir=bool(d.get("ogrenilir", False)),
        aciklama=str(d.get("aciklama") or ""),
        cekirdek=d["anahtar"] in CEKIRDEK,
        aktif=bool(d.get("aktif", True)),
        zorunlu=bool(d.get("zorunlu", False))) for d in girdiler])


VARSAYILAN = _coz(TOHUM)


def yaz(yol, s: Sema) -> None:
    """Şemayı atomik yazar (geçici dosya + os.replace): yarım kalan bir yazım
    kullanıcının tüm alan tanımlarını yok etmesin. Desen: `duzeltme.kurallari_yaz`."""
    gecici = str(yol) + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(s.json(), f, ensure_ascii=False, indent=2)
        os.replace(gecici, yol)
    except OSError:
        try:
            os.remove(gecici)
        except OSError:
            pass
        raise


def _yazmayi_dene(yol, s: Sema):
    try:
        yaz(yol, s)
    except OSError:
        pass        # salt okunur klasör: bellekteki şemayla devam et


def oku(yol) -> Sema:
    """Şemayı dosyadan okur; dosya yoksa tohumdan yazar. Hiç çökmez.

    Bozuk/tanınmayan dosyada tohumla devam edilir ve dosyaya **dokunulmaz**:
    içinde kullanıcının elle yazdığı tanımlar olabilir. Onarım gerektiyse
    (atanan anahtar/sütun) sonuç geri yazılır — atanan değer bir kez üretilir.
    """
    try:
        with open(yol, encoding="utf-8") as f:
            ham = json.load(f)
    except FileNotFoundError:
        _yazmayi_dene(yol, VARSAYILAN)
        return VARSAYILAN
    except (OSError, ValueError):
        return VARSAYILAN
    try:
        s = _coz(ham)
    except (ValueError, TypeError, AttributeError):
        # ponytail: hata sessiz; editör (#8) gelince kullanıcıya gösterilmeli
        return VARSAYILAN
    if s.json() != ham:
        _yazmayi_dene(yol, s)
    return s
