"""
Fatura işleme döngüsü — arka plan thread'inde çalışan saf iş mantığı.

UI'dan bağımsızdır; dış dünyayla yalnızca `log_q` kuyruğu ve `stop_event`
üzerinden konuşur. Bu sayede tkinter olmadan test edilebilir.
"""

import concurrent.futures
import glob
import os
import queue
import threading

import google.genai as genai

from extraction import (
    xml_den_veri_cek, pdf_den_veri_cek, pdf_text_ayikla,
    APIKeyHatasi, InternetHatasi, PDFHatasi, XMLHatasi,
    ModelHatasi,
    TIMEOUT_SANIYE, MAX_WORKERS, veri_dogrula,
    pdf_gecerli_mi,
)
from excel_utils import mevcut_verileri_oku


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

    yeni_satirlar = []
    atlanmis      = []
    uyari_listesi = []   # [(dosya_adi, [uyari, ...]), ...]
    siradaki = 0

    def islendi(veri):
        nonlocal siradaki
        yeni_satirlar.append(veri)
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
            dosya_adi = os.path.basename(veri.get("dosya_yolu") or "bilinmiyor")
            uyari_listesi.append((dosya_adi, uyarilar))

    def _bitir(kesildi=False):
        """İşlem sonu: yeni satır varsa onaya gönder, yoksa done yayınla."""
        if yeni_satirlar:
            log_q.put(("review", {
                "mevcut":   mevcut_satirlar,
                "yeni":     yeni_satirlar,
                "atlanmis": atlanmis,
                "uyarilar": uyari_listesi,
                "cikti":    CIKTI,
                "kesildi":  kesildi,
            }))
        else:
            log("info", "Kaydedilecek yeni fatura bulunamadı.")
            log_q.put(("done", (atlanmis, 0, uyari_listesi)))

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

            # Metni bir kez çıkar; hem log etiketi hem de işleme için kullan
            metin = pdf_text_ayikla(dosya)
            tip_etiketi = "Dijital" if len(metin) > 100 else "OCR"
            log("info", f"→  {dosya_adi[:50]:<51} ({tip_etiketi})")

            try:
                return ("ok", pdf_den_veri_cek(dosya, client, log_q, stop_event,
                                               zoom, metin=metin))
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
                    _bitir(kesildi=True)
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

    # ── İşlem sonu: onaya gönder ───────────────────────────────────────
    _bitir(kesildi=stop_event.is_set())
