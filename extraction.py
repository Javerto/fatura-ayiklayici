"""
PDF ve XML faturalardan veri çıkarma modülü.
"""

import google.genai as genai
from google.genai import types
import fitz
import xml.etree.ElementTree as ET
import json, os, re, time, pathlib, queue, threading
from datetime import datetime as _dt
from collections import deque

# ─── AYARLAR ─────────────────────────────────────────────────────────────────
GEMMA_MODEL      = "gemma-4-31b-it"
MAX_DENEME       = 5
TIMEOUT_SANIYE   = 180
THINKING_BUDGET  = -1
MAX_WORKERS      = 5    # paralel thread sayısı
RPM_LIMIT        = 14   # dakikada max istek (limitin biraz altında güvenli taraf)
# ─────────────────────────────────────────────────────────────────────────────

# ─── RATE LIMITER ─────────────────────────────────────────────────────────────
_rpm_lock      = threading.Lock()
_istek_zamanlari: deque = deque()   # son 60 saniyedeki istek zamanları

def _rpm_bekle():
    """Dakikada RPM_LIMIT isteği aşmamak için gerekirse bekler."""
    while True:
        with _rpm_lock:
            simdi = time.monotonic()
            # 60 saniyeden eski kayıtları temizle
            while _istek_zamanlari and simdi - _istek_zamanlari[0] >= 60:
                _istek_zamanlari.popleft()
            if len(_istek_zamanlari) < RPM_LIMIT:
                _istek_zamanlari.append(simdi)
                return
            # En eski isteğin 60 saniyesi dolana kadar beklenecek süre
            bekle = 60 - (simdi - _istek_zamanlari[0]) + 0.1
        time.sleep(bekle)
# ─────────────────────────────────────────────────────────────────────────────

# ─── ÖZEL HATALAR ─────────────────────────────────────────────────────────────
class APIKeyHatasi(Exception):
    """API key geçersiz veya süresi dolmuş — tüm işlem durur."""

class InternetHatasi(Exception):
    """Bağlantı veya limit hatası — bu fatura atlanır."""

class PDFHatasi(Exception):
    """PDF açılamadı — bu fatura atlanır."""

class XMLHatasi(Exception):
    """XML formatı geçersiz — bu fatura atlanır."""

class ModelHatasi(Exception):
    """AI modelinden geçersiz veya ayrıştırılamayan yanıt — bu fatura atlanır."""

class ExcelHatasi(Exception):
    """Excel kaydedilemedi."""
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_SABLON = """Ekteki fatura görsellerini dikkatlice incele. Aşağıdaki alanları çıkar.
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
    s = str(val).strip()
    try:
        if "," in s:
            # TR format: 1.234,56
            return float(s.replace(".", "").replace(",", "."))
        try:
            # Standart: 1000.00 veya 1234
            return float(s)
        except ValueError:
            # Son çare: yalnızca gerçek TR binlik nokta formatıysa (1.234, 1.234.567)
            if re.match(r'^\d{1,3}(\.\d{3})+$', s):
                return float(s.replace(".", ""))
            return None
    except (ValueError, TypeError):
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
        fixed  = prefix + seq.replace('0', '', 1)
        if len(fixed) == 16:
            return fixed, True
    return fn, False


def veri_dogrula(veri: dict) -> list[str]:
    """Fatura verisindeki olası sorunları uyarı listesi olarak döner.

    Dönüş değeri boşsa veri temiz demektir.
    Uyarılar işlemi durdurmaz — kullanıcıya log'da gösterilir.
    """
    uyarilar = []

    # fatura_no — boş veya tamamen sayısal
    fn = str(veri.get("fatura_no") or "").strip()
    if not fn:
        uyarilar.append("Fatura no boş")
    else:
        if re.sub(r"[\-/\s_.]", "", fn).isdigit():
            uyarilar.append(f"Fatura no yalnızca rakam: '{fn}' — format kontrolü yapın")
        if len(fn) != 16:
            uyarilar.append(
                f"Fatura no uzunluğu {len(fn)} karakter, otomatik düzeltilemedi — 16 olmalı: '{fn}'"
            )

    # sira_no — 3 haneden büyükse muhtemelen teşvik no ile karışmış
    sn = veri.get("sira_no")
    if sn is not None and sn >= 1000:
        uyarilar.append(
            f"Sıra no {int(sn)} — 3 haneden büyük, teşvik belgesi no ile karışmış olabilir")

    # vkn — 10-11 rakam olmalı
    vkn = str(veri.get("vkn") or "").strip()
    if not vkn:
        uyarilar.append("VKN boş")
    elif not vkn.isdigit() or len(vkn) not in (10, 11):
        uyarilar.append(f"VKN '{vkn}' geçersiz format (10-11 rakam olmalı)")

    # vergiler_dahil_tutar — zorunlu, pozitif
    vdt = veri.get("vergiler_dahil_tutar")
    if vdt is None:
        uyarilar.append("Vergiler dahil tutar boş")
    elif vdt <= 0:
        uyarilar.append(f"Vergiler dahil tutar sıfır/negatif: {vdt}")

    # fatura_tarihi — parse edilememiş string olarak kaldıysa
    tarih = veri.get("fatura_tarihi")
    if isinstance(tarih, str) and tarih:
        uyarilar.append(f"Tarih okunamadı: '{tarih}'")

    # para_birimi — bilinen listede olmayan değer
    pb = str(veri.get("para_birimi") or "").strip().upper()
    if pb and pb not in _BILINEN_PARA_BIRIMLERI:
        uyarilar.append(f"Bilinmeyen para birimi: '{pb}'")

    # sirket_adi — boş olmamalı
    if not str(veri.get("sirket_adi") or "").strip():
        uyarilar.append("Şirket adı boş")

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
        desc_el = (ilk_kalem.find("cac:Item/cbc:Description", NS)
                   or ilk_kalem.find("cac:Item/cbc:Name", NS))
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


def pdf_den_veri_cek(dosya_yolu: str, client, log_q: queue.Queue,
                     stop_event: threading.Event | None = None,
                     zoom: float = 1.5) -> dict:
    """PDF sayfalarını görsel olarak AI'ya gönderir, JSON yanıtı döner."""
    images = pdf_to_images(dosya_yolu, zoom)

    parts = [PROMPT_SABLON]
    for img_bytes in images:
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

    think_cfg = None
    if THINKING_BUDGET == 0:
        think_cfg = types.ThinkingConfig(thinking_budget=0)
    elif THINKING_BUDGET > 0:
        think_cfg = types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
    gen_config = types.GenerateContentConfig(thinking_config=think_cfg) if think_cfg else None

    TEKRAR_HATALARI  = ("429", "resource_exhausted", "503", "504", "unavailable",
                        "deadline_exceeded", "ssl", "timeout", "readtimeout",
                        "connecttimeout", "connectionerror", "remoteprotocolerror", "recv")
    API_KEY_HATALARI = ("api_key_invalid", "api key", "invalid_api_key",
                        "permission_denied", "unauthenticated")

    son_hata = None
    for deneme in range(MAX_DENEME):
        _rpm_bekle()
        if stop_event and stop_event.is_set():
            raise InternetHatasi("İşlem durduruldu.")
        try:
            response = client.models.generate_content(
                model=GEMMA_MODEL, contents=parts, config=gen_config)
            son_hata = None
            break
        except Exception as e:
            hata_str = str(e).lower()
            if any(k in hata_str for k in API_KEY_HATALARI):
                raise APIKeyHatasi(
                    "API key geçersiz veya süresi dolmuş.\n"
                    "Lütfen geçerli bir key girin (aistudio.google.com).")
            if any(k in hata_str for k in TEKRAR_HATALARI):
                son_hata = e
                bekle = 15 * (deneme + 1)
                m = re.search(r"retry[^0-9]*([0-9]+)s", str(e), re.IGNORECASE)
                if m:
                    bekle = int(m.group(1)) + 2
                log_q.put(("info", f"   ↻ Bağlantı hatası, {bekle}s bekleniyor "
                                   f"(deneme {deneme + 1}/{MAX_DENEME})..."))
                for _ in range(bekle):
                    if stop_event and stop_event.is_set():
                        raise InternetHatasi("İşlem durduruldu.")
                    time.sleep(1)
            else:
                son_hata = e
                break

    if son_hata:
        hata_str = (str(son_hata) + " " + type(son_hata).__name__).lower()
        if any(k in hata_str for k in ("timeout", "connection", "network", "ssl", "recv")):
            raise InternetHatasi(
                "İnternet bağlantısı kurulamadı veya istek zaman aşımına uğradı. "
                "Bağlantınızı kontrol edip tekrar deneyin.")
        if "429" in hata_str or "rate" in hata_str or "quota" in hata_str:
            raise InternetHatasi(
                "API istek limiti aşıldı. Birkaç dakika bekleyip tekrar başlatın.")
        raise son_hata

    cevap = response.text.strip()
    if cevap.startswith("```"):
        cevap = cevap.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        veri = json.loads(cevap)
    except json.JSONDecodeError:
        raise ModelHatasi("Modelden geçersiz JSON yanıtı alındı. Dosya atlanıyor.")

    raw_fn = str(veri.get("fatura_no") or "").strip()
    if raw_fn:
        veri["fatura_no"], _ = _duzelt_fatura_no(raw_fn)
    veri["fatura_tarihi"] = tarih_parse(str(veri.get("fatura_tarihi", "") or ""))
    for alan in ("toplam_miktar", "kdv_haric_tutar", "vergiler_dahil_tutar", "sira_no"):
        veri[alan] = to_float(veri.get(alan))
    veri["dosya_yolu"] = str(pathlib.Path(dosya_yolu).resolve())
    return veri
