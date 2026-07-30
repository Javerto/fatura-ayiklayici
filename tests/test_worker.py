"""worker — uçtan uca işleme döngüsü (XML-only, AI gerektirmez).

Bu test worker'ın gui'den ayrılması (refactor) sırasında davranışın
korunduğunu garanti eder ve worker döngüsünün tek entegrasyon testidir.
"""

import pathlib
import queue
import shutil
import threading

import pytest

# worker'ın bulunduğu modül (taşıma sonrası 'worker' modülü)
from worker import worker

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ornek_fatura.xml"


@pytest.fixture(autouse=True)
def sahte_genai_client(monkeypatch):
    """genai.Client'ı ağ çağrısı yapmadan oluştur (XML için kullanılmaz)."""
    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kw: object())


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
