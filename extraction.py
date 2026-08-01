"""
PDF ve XML faturalardan veri çıkarma modülü.
"""

import fitz
import xml.etree.ElementTree as ET
import json, os, re, pathlib
from datetime import datetime as _dt

from hatalar import PDFHatasi, XMLHatasi, ModelHatasi

# ─── AYARLAR ─────────────────────────────────────────────────────────────────
MAX_WORKERS = 5    # paralel thread sayısı
# Model çağrısına ait ayarlar (model adı, deneme sayısı, RPM, timeout)
# gemini.py'de: bu modül artık modelle nasıl konuşulduğunu bilmiyor.
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

PROMPT_SABLON = """Fatura verilerini (görsel veya metin) dikkatlice incele. Aşağıdaki alanları çıkar.
SADECE geçerli JSON döndür, başka hiçbir şey yazma, kod bloğu kullanma.

{
  "fatura_no": "fatura numarası — Türk e-fatura standardı: 3 karakter (büyük harf veya rakam) + 4 haneli yıl + 9 haneli sıra, toplam 16 karakter (örn: GIB2024000000001). Fazladan sıfır EKLEME.",
  "fatura_tarihi": "GG.AA.YYYY formatında tarih",
  "sirket_adi": "faturayı kesen SATICI şirketin adı. Faturada iki şirket varsa ALICI değil SATICI olanı yaz.",
  "tanim": "ilk kalem ya da ana hizmetin açıklaması",
  "toplam_miktar": toplam adet/miktar (sadece sayı, örnek: 7 veya 14.5),
  "kdv_haric_tutar": KDV hariç Mal/Hizmet Toplam Tutarı, TL cinsinden sayı. EUR ve TL varsa TL ver. Yoksa null,
  "vergiler_dahil_tutar": Vergiler Dahil Toplam Tutar, TL cinsinden sayı. "Ödenecek Tutar(TL)" veya "Vergiler Dahil Toplam Tutar(TL)" satırını bul. EUR/TL karışıksa TL ver,
  "para_birimi": "TL ya da yalnızca döviz varsa EUR veya USD",
  "vkn": "SATICI şirketin VKN'i (10-11 haneli). Faturada birden fazla VKN varsa SATICI olana ait olanı yaz.",
  "vergi_dairesi": "satıcı şirketin vergi dairesi adı",
  "sira_no": yatırım teşvik belgesinin kaçıncı sıra nosu — SADECE şu kalıplardan birinde geçiyorsa al: "X sırasında KDV istisnası", "Yerli Liste X sırasında", "Sıra No: X kapsamında","Liste Y-x sıra numarasına istinaden". Diğer no alanlarını ASLA alma. Yoksa null
}"""

SIRA_PATTERN = re.compile(
    r'(\d+)\s*s[ıi]ras[ıi]nda\s*KDV'
    r'|Yerli\s+Liste\s+(\d+)\s*s[ıi]ras[ıi]nda'
    r'|S[ıi]ra\s*No[:\s]+(\d+)\s*kapsam[ıi]nda'
    r'|Liste\s+\S+-(\d+)\s*s[ıi]ra\s+numaras[ıi]na',
    re.IGNORECASE
)

_BILINEN_PARA_BIRIMLERI = {"TL", "TRY", "EUR", "USD"}

# Türkiye'de geçerli/yaygın KDV oranları (örtük oran kontrolü için)
KDV_ORANLARI = (0, 1, 8, 10, 18, 20)


# ─── YARDIMCILAR ─────────────────────────────────────────────────────────────

def tarih_parse(tarih_str):
    """Tarih stringini datetime nesnesine çevirir, başaramazsa orijinali döner."""
    if not tarih_str:
        return tarih_str
    tarih_temiz = re.sub(r'\s', '', str(tarih_str))
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return _dt.strptime(tarih_temiz[:10], fmt)
        except ValueError:
            continue
    return tarih_str


# Sayının kendisi: baştaki/sondaki sembol ve birimleri ("₺", "TL", "adet") eler.
_SAYI_KALIBI = re.compile(r"-?\d[\d.,]*")
# Nokta yalnızca binlik ayırıcıysa: 1.234 · 1.234.567 (ama 14.5 veya 1000.00 değil)
_BINLIK_NOKTA = re.compile(r"-?\d{1,3}(\.\d{3})+")


def to_float(val):
    """String ya da sayıyı float'a çevirir, başaramazsa None döner.

    Format algılama:
      - Virgül varsa → TR formatı (1.234,56 → 1234.56)
      - Virgül yoksa → standart ondalık (1000.00 → 1000.0)
        Standart parse başarısız olursa TR binlik nokta dener (1.234 → 1234)
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)

    m = _SAYI_KALIBI.search(str(val))
    if not m:
        return None
    s = m.group(0).rstrip(".,")      # "12,50 TL" → "12,50",  "1.234." → "1.234"

    nokta, virgul = s.rfind("."), s.rfind(",")
    if nokta >= 0 and virgul >= 0:
        # İkisi de varsa SONRAKİ ayırıcı ondalıktır; diğeri binliktir.
        # 1.234,56 → 1234.56   ·   1,234.56 → 1234.56
        s = s.replace(",", "") if nokta > virgul \
            else s.replace(".", "").replace(",", ".")
    elif virgul >= 0:
        # Tek virgül TR ondalığıdır (1000,50); birden fazlaysa binliktir (1,234,567).
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif _BINLIK_NOKTA.fullmatch(s):
        # 1.234 / 1.234.567 → binlik nokta. 14.5 ve 1000.00 buraya girmez.
        s = s.replace(".", "")

    try:
        return float(s)
    except ValueError:
        return None


def _duzelt_fatura_no(fn: str) -> tuple[str, bool]:
    """17 karakter fatura_no'dan fazla 0'ı temizler.

    Türk e-fatura formatı: [A-Z]{3} + 4 haneli yıl + 9 haneli sıra = 16 char.
    Gemini zaman zaman sıra bölümüne fazladan bir 0 ekliyor.
    Düzeltildiyse (fixed_fn, True), değişiklik yoksa (fn, False) döner.
    """
    fn = fn.strip()
    if len(fn) == 17 and re.match(r'^[A-Z0-9]{3}\d{14}$', fn):
        prefix = fn[:7]   # 3 harf + 4 haneli yıl
        seq    = fn[7:]   # 10 haneli sıra (1 fazla)
        # Yalnızca baştan fazla 0 varsa temizle. Baştan sıfır yoksa hangi
        # hanenin fazla olduğu belirsizdir; ortadaki meşru sıfırı silip
        # numarayı bozmak yerine olduğu gibi bırakırız (veri_dogrula uyarır).
        if seq.startswith('0'):
            fixed = prefix + seq[1:]
            if len(fixed) == 16:
                return fixed, True
    return fn, False


def _json_ayikla(cevap: str) -> dict:
    """Model yanıtından JSON nesnesini çıkarır.

    ``` kod bloklarını (json etiketli veya etiketsiz) ve JSON'ın etrafındaki
    açıklama metnini tolere eder. Geçerli bir JSON *nesnesi* bulunamazsa
    ModelHatasi fırlatır.
    """
    s = (cevap or "").strip()

    # Varsa ``` ... ``` kod bloğunun içeriğini al (metnin neresinde olursa olsun)
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()

    # Önce tüm metni dene; olmazsa ilk '{' ile son '}' arasını dene (prose sarmalı)
    adaylar = [s]
    ilk, son = s.find("{"), s.rfind("}")
    if ilk != -1 and son > ilk:
        adaylar.append(s[ilk:son + 1])

    for aday in adaylar:
        try:
            veri = json.loads(aday)
        except json.JSONDecodeError:
            continue
        if isinstance(veri, dict):
            return veri

    raise ModelHatasi("Modelden geçersiz JSON yanıtı alındı. Dosya atlanıyor.")


def veri_dogrula(veri: dict) -> list[tuple[str, str]]:
    """Fatura verisindeki olası sorunları (alan, mesaj) çiftleri olarak döner.

    Dönüş değeri boşsa veri temiz demektir.
    Uyarılar işlemi durdurmaz — kullanıcıya gösterilir.

    Alan adı, uyarının hangi düzenlenebilir alandan kaynaklandığını söyler;
    gözden geçirme ekranı uyarıyı o alanın altında gösterir.
    """
    uyarilar = []

    def ekle(alan, mesaj):
        uyarilar.append((alan, mesaj))

    # fatura_no — boş veya tamamen sayısal
    fn = str(veri.get("fatura_no") or "").strip()
    if not fn:
        ekle("fatura_no", "Fatura no boş")
    else:
        if re.sub(r"[\-/\s_.]", "", fn).isdigit():
            ekle("fatura_no", f"Fatura no yalnızca rakam: '{fn}' — format kontrolü yapın")
        if len(fn) != 16:
            ekle("fatura_no",
                 f"Fatura no uzunluğu {len(fn)} karakter, otomatik düzeltilemedi — 16 olmalı: '{fn}'")

    # sira_no — 3 haneden büyükse muhtemelen teşvik no ile karışmış
    sn = veri.get("sira_no")
    if sn is not None and sn >= 1000:
        ekle("sira_no",
             f"Sıra no {int(sn)} — 3 haneden büyük, teşvik belgesi no ile karışmış olabilir")

    # vkn — 10-11 rakam olmalı
    vkn = str(veri.get("vkn") or "").strip()
    if not vkn:
        ekle("vkn", "VKN boş")
    elif not vkn.isdigit() or len(vkn) not in (10, 11):
        ekle("vkn", f"VKN '{vkn}' geçersiz format (10-11 rakam olmalı)")

    # vergiler_dahil_tutar — zorunlu, pozitif
    vdt = veri.get("vergiler_dahil_tutar")
    if vdt is None:
        ekle("vergiler_dahil_tutar", "Vergiler dahil tutar boş")
    elif vdt <= 0:
        ekle("vergiler_dahil_tutar", f"Vergiler dahil tutar sıfır/negatif: {vdt}")

    # tutar tutarlılığı — örtük KDV oranı bilinen oranlardan birine uymalı
    kht = veri.get("kdv_haric_tutar")
    if (isinstance(vdt, (int, float)) and isinstance(kht, (int, float))
            and vdt > 0 and kht > 0):
        if vdt < kht:
            ekle("vergiler_dahil_tutar",
                 f"Vergiler dahil tutar ({vdt}) KDV hariç tutardan ({kht}) küçük")
        else:
            oran = (vdt - kht) / kht * 100
            if not any(abs(oran - o) <= 0.5 for o in KDV_ORANLARI):
                ekle("vergiler_dahil_tutar",
                     f"Örtük KDV oranı %{oran:.1f} bilinen oranlara "
                     f"(0/1/8/10/18/20) uymuyor — tutarları kontrol edin")

    # fatura_tarihi — boş, ya da parse edilememiş string olarak kaldıysa
    tarih = veri.get("fatura_tarihi")
    if not tarih:
        ekle("fatura_tarihi", "Fatura tarihi boş")
    elif isinstance(tarih, str):
        ekle("fatura_tarihi", f"Tarih okunamadı: '{tarih}'")

    # para_birimi — bilinen listede olmayan değer
    pb = str(veri.get("para_birimi") or "").strip().upper()
    if pb and pb not in _BILINEN_PARA_BIRIMLERI:
        ekle("para_birimi", f"Bilinmeyen para birimi: '{pb}'")

    # sirket_adi — boş olmamalı
    if not str(veri.get("sirket_adi") or "").strip():
        ekle("sirket_adi", "Şirket adı boş")

    return uyarilar


# ─── VERİ ÇIKARMA ─────────────────────────────────────────────────────────────

def pdf_gecerli_mi(dosya: str) -> bool:
    """PDF açılabilir mi kontrol eder; handle'ı her durumda kapatır."""
    try:
        doc = fitz.open(dosya)
        doc.close()
        return True
    except Exception:
        return False


def pdf_to_images(dosya_yolu: str, zoom: float = 1.5) -> list[bytes]:
    try:
        doc = fitz.open(dosya_yolu)
    except Exception:
        raise PDFHatasi("PDF açılamadı. Dosya bozuk veya şifreli olabilir.")
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        images.append(pix.tobytes("jpeg"))
    doc.close()
    if not images:
        raise PDFHatasi("PDF'den görsel oluşturulamadı. Sayfa içeriği boş olabilir.")
    return images


def xml_den_veri_cek(xml_yolu: str, pdf_yolu: str | None) -> dict:
    """UBL XML faturadan veri çıkarır. pdf_yolu None ise sadece XML vardır."""
    NS = {
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }
    try:
        root = ET.parse(xml_yolu).getroot()
    except ET.ParseError as e:
        raise XMLHatasi(f"XML okunamadı. Geçerli bir UBL e-fatura olmayabilir. ({e})")

    def bul(yol):
        el = root.find(yol, NS)
        return el.text.strip() if el is not None and el.text else None

    fatura_no = bul("cbc:ID")
    if fatura_no:
        fatura_no, _ = _duzelt_fatura_no(fatura_no)
    tarih_str = bul("cbc:IssueDate")

    satici = "cac:AccountingSupplierParty/cac:Party"
    sirket_adi    = bul(f"{satici}/cac:PartyName/cbc:Name")
    vkn           = bul(f"{satici}/cac:PartyTaxScheme/cbc:CompanyID")
    vergi_dairesi = bul(f"{satici}/cac:PartyTaxScheme/cac:TaxScheme/cbc:Name")

    kdv_haric = bul("cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount")
    vergili   = bul("cac:LegalMonetaryTotal/cbc:PayableAmount")
    para_el   = root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS)
    para_birimi = para_el.get("currencyID", "TL") if para_el is not None else "TL"

    tanim = None
    ilk_kalem = root.find("cac:InvoiceLine", NS)
    if ilk_kalem is not None:
        # Not: Element üzerinde `A or B` kullanılamaz — çocuğu olmayan bir
        # element (metni olsa bile) falsy değerlendirilir, bu yüzden açıkça
        # `is None` kontrolü yapıyoruz.
        desc_el = ilk_kalem.find("cac:Item/cbc:Description", NS)
        if desc_el is None:
            desc_el = ilk_kalem.find("cac:Item/cbc:Name", NS)
        if desc_el is not None and desc_el.text:
            tanim = desc_el.text.strip()

    toplam_miktar = 0.0
    for kalem in root.findall("cac:InvoiceLine", NS):
        miktar_el = kalem.find("cbc:InvoicedQuantity", NS)
        if miktar_el is not None and miktar_el.text:
            try:
                toplam_miktar += float(miktar_el.text.strip())
            except ValueError:
                pass

    sira_no = None
    for note in root.findall(".//cbc:Note", NS):
        if note.text:
            m = SIRA_PATTERN.search(note.text)
            if m:
                sira_no = float(next(g for g in m.groups() if g))
                break

    dosya_yolu = str(pathlib.Path(pdf_yolu).resolve()) if pdf_yolu else str(pathlib.Path(xml_yolu).resolve())

    return {
        "fatura_no":            fatura_no,
        "fatura_tarihi":        tarih_parse(tarih_str),
        "sirket_adi":           sirket_adi,
        "tanim":                tanim,
        "toplam_miktar":        toplam_miktar or None,
        "kdv_haric_tutar":      to_float(kdv_haric),
        "vergiler_dahil_tutar": to_float(vergili),
        "para_birimi":          para_birimi,
        "vkn":                  vkn,
        "vergi_dairesi":        vergi_dairesi,
        "sira_no":              sira_no,
        "dosya_yolu":           dosya_yolu,
    }


def pdf_text_ayikla(dosya_yolu: str) -> str:
    """PDF'den dijital metni ayıklar."""
    try:
        doc = fitz.open(dosya_yolu)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception:
        return ""


def pdf_den_veri_cek(dosya_yolu: str, istemci, zoom: float = 1.5,
                     metin: str | None = None) -> dict:
    """
    Hibrid yöntem: Önce dijital metni çekmeyi dener, bulamazsa görsele başvurur.

    `metin` dışarıdan verilirse (çağıran zaten çıkarmışsa) tekrar çıkarılmaz.
    `istemci` modelle konuşmanın tek kapısı (bkz. gemini.ModelIstemcisi);
    hız sınırı, yeniden deneme ve hata sınıflandırma onun ardında kalır.
    """
    # 1. Metin verilmediyse çıkar (verildiyse çift çıkarmayı önle)
    if metin is None:
        metin = pdf_text_ayikla(dosya_yolu)

    parcalar = [PROMPT_SABLON]
    is_digital = len(metin) > 100   # Anlamlı bir metin varsa dijital kabul et

    if is_digital:
        parcalar.append(f"\n\nFatura Metni İçeriği:\n{metin}")
    else:
        # 2. Metin yoksa veya çok azsa görsele başvur (Fallback)
        parcalar.extend(pdf_to_images(dosya_yolu, zoom))

    veri = _json_ayikla(istemci.metin_uret(parcalar))

    raw_fn = str(veri.get("fatura_no") or "").strip()
    if raw_fn:
        veri["fatura_no"], _ = _duzelt_fatura_no(raw_fn)
    veri["fatura_tarihi"] = tarih_parse(str(veri.get("fatura_tarihi", "") or ""))
    for alan in ("toplam_miktar", "kdv_haric_tutar", "vergiler_dahil_tutar", "sira_no"):
        veri[alan] = to_float(veri.get(alan))
    veri["dosya_yolu"] = str(pathlib.Path(dosya_yolu).resolve())
    veri["_teknik_bilgi"] = "Dijital" if is_digital else "OCR"
    return veri
