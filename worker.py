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
import time

import gemini
from extraction import (
    xml_den_veri_cek, pdf_den_veri_cek, pdf_text_ayikla,
    MAX_WORKERS, veri_dogrula, pdf_gecerli_mi,
)
from hatalar import (APIKeyHatasi, InternetHatasi, PDFHatasi, XMLHatasi,
                     ModelHatasi, ExcelHatasi)
from excel_utils import mevcut_verileri_oku
from duzeltme import kural_uygula


def worker(api_key: str, klasor: str, cikti_adi: str, log_q: queue.Queue,
           stop_event: threading.Event, retry_dosyalar: list | None = None,
           zoom: float = 1.5, kurallar: dict | None = None, istemci=None):
    """Fatura işleme döngüsü — ayrı thread'de çalışır.

    `istemci` verilmezse gerçek Gemini istemcisi kurulur; testler kendi
    sahtelerini geçirerek tüm döngüyü ağa çıkmadan çalıştırır.
    """

    def log(tag, mesaj):
        log_q.put((tag, mesaj))

    kurallar = kurallar or {}

    if istemci is None:
        try:
            istemci = gemini.olustur(
                api_key,
                bilgi=lambda mesaj: log_q.put(("info", mesaj)),
                iptal=stop_event)
        except Exception as e:
            log("critical", f"Bağlantı kurulamadı: {e}")
            log_q.put(("done", ([], 0, [])))
            return

    CIKTI = os.path.join(klasor, cikti_adi)

    if retry_dosyalar is not None:
        islenmemis_pdf = [d for d in retry_dosyalar if not d.lower().endswith(".xml")]
        islenmemis_xml = [d for d in retry_dosyalar if d.lower().endswith(".xml")]
        toplam = len(islenmemis_pdf) + len(islenmemis_xml)
        try:
            mevcut_satirlar, _ = mevcut_verileri_oku(CIKTI)
        except ExcelHatasi as e:
            log("critical", str(e))
            log_q.put(("done", ([], 0, [])))
            return
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

        try:
            mevcut_satirlar, islenenmis = mevcut_verileri_oku(CIKTI)
        except ExcelHatasi as e:
            log("critical", str(e))
            log_q.put(("done", ([], 0, [])))
            return
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
        veri = kural_uygula(veri, kurallar)
        yeni_satirlar.append(veri)
        siradaki += 1
        log_q.put(("progress", (siradaki, toplam)))
        uyarilar = veri_dogrula(veri)
        dosya_yolu = str(veri.get("dosya_yolu") or "")
        dosya_adi = os.path.basename(dosya_yolu) or "bilinmiyor"
        # Süre yalnızca arayüz içindir; Excel'e sızmasın diye pop ile alınır.
        log_q.put(("fatura", {
            "dosya":       dosya_adi,
            "fatura_no":   veri.get("fatura_no") or "-",
            "sirket_adi":  veri.get("sirket_adi") or "-",
            "tutar":       veri.get("vergiler_dahil_tutar"),
            "para_birimi": veri.get("para_birimi") or "TRY",
            "kaynak":      veri.get("_teknik_bilgi")
                           or ("XML" if dosya_yolu.lower().endswith(".xml") else ""),
            "uyarilar":    uyarilar,
            "sure":        veri.pop("_sure", None),
        }))
        if uyarilar:
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
        log_q.put(("atlandi", {"dosya": dosya_adi, "sebep": sebep}))
        atlanmis.append((dosya_adi, sebep))

    def sureli(veri, t0):
        """Çıkarılan satıra işlem süresini ekler (arayüzde gösterilir)."""
        veri["_sure"] = round(time.time() - t0, 1)
        return veri

    # ── PDF dosyaları (paralel) ────────────────────────────────────────
    api_hata = threading.Event()

    def pdf_gorevi(dosya):
        if stop_event.is_set() or api_hata.is_set():
            return None
        dosya_adi = os.path.basename(dosya)
        xml_yolu  = os.path.splitext(dosya)[0] + ".xml"
        t0 = time.time()
        if os.path.exists(xml_yolu):
            log_q.put(("isleniyor", {"dosya": dosya_adi, "tip": "XML"}))
            try:
                veri = xml_den_veri_cek(xml_yolu, dosya)
                # dosya_yolu PDF'i gösterdiği için excel_utils'in .xml
                # fallback'i tutmuyor; kaynağı burada işaretlemezsek
                # Kaynak sütunu boş kalıyor.
                veri.setdefault("_teknik_bilgi", "XML")
                return ("ok", sureli(veri, t0))
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
            # Dosya adı ve tip ayrı gider: arayüz uçan işleri biten faturayla
            # ("fatura"/"atlandi" olaylarının `dosya` alanı) eşleştiriyor.
            log_q.put(("isleniyor", {"dosya": dosya_adi, "tip": tip_etiketi}))

            try:
                return ("ok", sureli(pdf_den_veri_cek(dosya, istemci, zoom,
                                                      metin=metin), t0))
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

        kritik_bildirildi = False

        def biteni_topla(futures) -> bool:
            """Tamamlanmış görevlerin sonucunu işler; devam edilsin mi döner.

            Kritik hatada erken dönmez: aynı turda tamamlanmış diğer faturalar
            da kaydedilmeli, yoksa cevabı gelmiş iş çöpe gider.
            """
            nonlocal kritik_bildirildi
            devam = True
            for future in futures:
                if not future.done() or future.cancelled():
                    continue
                sonuc = future.result()
                if sonuc is None:
                    continue
                tip, veri = sonuc
                if tip == "ok":
                    islendi(veri)
                elif tip == "atla":
                    atla(*veri)
                elif tip == "critical":
                    devam = False
                    if not kritik_bildirildi:   # 5 thread aynı hatayı verebilir
                        kritik_bildirildi = True
                        log("critical", str(veri))
            return devam

        while bekleyen:
            if stop_event.is_set():
                for f in bekleyen:
                    f.cancel()
                # Cevabı gelmiş ama henüz okunmamış faturaları atmadan al:
                # API parası harcanmış, sonucu çöpe atmanın anlamı yok.
                biteni_topla(bekleyen)
                log("info", "İşlem kullanıcı tarafından durduruldu.")
                break

            biten, bekleyen = concurrent.futures.wait(
                bekleyen, timeout=1,
                return_when=concurrent.futures.FIRST_COMPLETED)

            if not biteni_topla(biten):          # API key hatası
                for f in bekleyen:
                    f.cancel()
                # Aynı turda tamamlanmış diğer faturalar da kurtarılmalı.
                biteni_topla(bekleyen)
                _bitir(kesildi=True)
                return

    # ── XML-only dosyalar ──────────────────────────────────────────────
    for xml_dosya in islenmemis_xml:
        if stop_event.is_set():
            log("info", "İşlem kullanıcı tarafından durduruldu.")
            break

        dosya_adi = os.path.basename(xml_dosya)
        log_q.put(("isleniyor", {"dosya": dosya_adi, "tip": "XML"}))
        t0 = time.time()
        try:
            islendi(sureli(xml_den_veri_cek(xml_dosya, None), t0))
        except XMLHatasi as e:
            atla(dosya_adi, str(e))
        except Exception as e:
            atla(dosya_adi, f"Beklenmedik hata — {type(e).__name__}: {e}")

    # ── İşlem sonu: onaya gönder ───────────────────────────────────────
    _bitir(kesildi=stop_event.is_set())
