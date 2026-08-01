"""worker — uçtan uca işleme döngüsü.

Bu test worker'ın gui'den ayrılması (refactor) sırasında davranışın
korunduğunu garanti eder ve worker döngüsünün tek entegrasyon testidir.

PDF yolu, model çağrısı `gemini` dikişinin ardına alındıktan sonra test
edilebilir hâle geldi: `istemci` parametresine sahte geçiliyor, ağa çıkılmıyor.
"""

import pathlib
import queue
import shutil
import threading

import fitz

from worker import worker

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ornek_fatura.xml"


class SahteIstemci:
    """gemini.ModelIstemcisi yerine geçer; sırayla verilen yanıtları döndürür."""

    def __init__(self, *yanitlar):
        self._yanitlar = list(yanitlar)
        self.cagrilar = []

    def metin_uret(self, parcalar):
        self.cagrilar.append(parcalar)
        y = self._yanitlar.pop(0) if len(self._yanitlar) > 1 else self._yanitlar[0]
        if isinstance(y, Exception):
            raise y
        return y


def _pdf_olustur(yol, metin="FATURA BILGILERI SATIRI "):
    """Dijital metin katmanı olan gerçek bir PDF üretir (>100 karakter)."""
    doc = fitz.open()
    sayfa = doc.new_page()
    for i in range(10):
        sayfa.insert_text((72, 100 + i * 20), metin)
    doc.save(str(yol))
    doc.close()


def _kuyrugu_bosalt(log_q):
    mesajlar = []
    while True:
        try:
            mesajlar.append(log_q.get_nowait())
        except queue.Empty:
            return mesajlar


def test_worker_xml_only_review_yayinlar(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "fatura1.xml")
    log_q = queue.Queue()
    stop = threading.Event()

    worker("FAKE_KEY", str(tmp_path), "cikti.xlsx", log_q, stop)

    mesajlar = _kuyrugu_bosalt(log_q)
    tipler = [t for t, _ in mesajlar]
    assert "review" in tipler
    assert "done" not in tipler        # yeni satır var → review, done değil

    payload = next(d for t, d in mesajlar if t == "review")
    assert len(payload["yeni"]) == 1
    assert payload["atlanmis"] == []
    assert payload["kesildi"] is False

    # Worker ARTIK Excel yazmaz — yazım onaya ertelendi
    assert not (tmp_path / "cikti.xlsx").exists()


def test_worker_bos_klasor_uyari_verir(tmp_path):
    log_q = queue.Queue()
    stop = threading.Event()

    worker("FAKE_KEY", str(tmp_path), "cikti.xlsx", log_q, stop)

    mesajlar = _kuyrugu_bosalt(log_q)
    tags = [t for t, _ in mesajlar]
    assert "critical" in tags  # "işlenecek PDF veya XML yok"
    # Terminal olay da gitmeli: gitmezse arayüz sonsuza dek "işleniyor"da kalır.
    assert "done" in tags


def test_worker_kurallari_uygular(tmp_path):
    """vkn eşleşen kural, review payload'undaki satıra uygulanır."""
    shutil.copy(FIXTURE, tmp_path / "fatura1.xml")
    log_q = queue.Queue()
    stop = threading.Event()
    kurallar = {"1234567890": {"sirket_adi": "DÜZELTİLMİŞ A.Ş."}}

    worker("FAKE_KEY", str(tmp_path), "cikti.xlsx", log_q, stop,
           kurallar=kurallar)

    mesajlar = _kuyrugu_bosalt(log_q)
    payload = next(d for t, d in mesajlar if t == "review")
    assert payload["yeni"][0]["sirket_adi"] == "DÜZELTİLMİŞ A.Ş."


# ── PDF yolu (gemini dikişi sayesinde artık ağsız test edilebilir) ────────

def test_worker_pdf_faturasini_uctan_uca_isler(tmp_path):
    _pdf_olustur(tmp_path / "fatura1.pdf")
    istemci = SahteIstemci(
        '{"fatura_no": "GIB2024000000001", "fatura_tarihi": "15.01.2024",'
        ' "sirket_adi": "ORNEK A.S.", "vkn": "1234567890",'
        ' "kdv_haric_tutar": 1000, "vergiler_dahil_tutar": 1200,'
        ' "para_birimi": "TL"}')
    log_q = queue.Queue()

    worker("K", str(tmp_path), "cikti.xlsx", log_q, threading.Event(),
           istemci=istemci)

    payload = next(d for t, d in _kuyrugu_bosalt(log_q) if t == "review")
    satir = payload["yeni"][0]
    assert satir["fatura_no"] == "GIB2024000000001"
    assert satir["vergiler_dahil_tutar"] == 1200
    assert satir["_teknik_bilgi"] == "Dijital"   # metin katmanı vardı, OCR'a düşmedi
    # PDF'in metni modele gitmiş olmalı, görsel değil
    assert any("FATURA BILGILERI" in p for p in istemci.cagrilar[0]
               if isinstance(p, str))


def test_worker_model_hatasinda_faturayi_atlar(tmp_path):
    """Kalıcı model hatası tüm işi düşürmez, o faturayı atlar."""
    from hatalar import ModelHatasi

    _pdf_olustur(tmp_path / "bozuk.pdf")
    log_q = queue.Queue()

    worker("K", str(tmp_path), "cikti.xlsx", log_q, threading.Event(),
           istemci=SahteIstemci(ModelHatasi("Modelden geçersiz JSON yanıtı")))

    mesajlar = _kuyrugu_bosalt(log_q)
    atlandi = next(d for t, d in mesajlar if t == "atlandi")
    assert atlandi["dosya"] == "bozuk.pdf"
    assert "done" in [t for t, _ in mesajlar]    # terminal olay yine de gitmeli


def test_worker_api_key_hatasinda_tum_isi_durdurur(tmp_path):
    from hatalar import APIKeyHatasi

    _pdf_olustur(tmp_path / "a.pdf")
    _pdf_olustur(tmp_path / "b.pdf")
    log_q = queue.Queue()

    worker("K", str(tmp_path), "cikti.xlsx", log_q, threading.Event(),
           istemci=SahteIstemci(APIKeyHatasi("API key geçersiz")))

    mesajlar = _kuyrugu_bosalt(log_q)
    kritikler = [d for t, d in mesajlar if t == "critical"]
    assert len(kritikler) == 1                   # 5 thread aynı hatayı bağırmasın
    assert "API key" in kritikler[0]
