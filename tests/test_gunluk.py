"""Günlük dosyası: kullanıcıda olan hatanın izi diske düşmeli."""
import logging
import queue
import sys
import threading
from logging.handlers import RotatingFileHandler

import pytest

import main
from api import Api
from elogo_indir import indir


@pytest.fixture
def yol(tmp_path):
    """Günlük yolu. Kurulumu test gövdesi yapar: pytest thread kancasını her
    aşamada yeniden kurduğu için fixture'da kurulan kanca çağrı aşamasına kalmaz."""
    kancalar = sys.excepthook, threading.excepthook
    yield tmp_path / "gunluk.txt"
    sys.excepthook, threading.excepthook = kancalar
    kok = logging.getLogger()
    for h in [h for h in kok.handlers if isinstance(h, RotatingFileHandler)]:
        kok.removeHandler(h)
        h.close()          # Windows'ta açık dosya tmp_path temizliğini engeller


def test_uygulama_hatasi_iziyle_dosyaya_yazilir(yol):
    main.gunluk_kur(yol)
    try:
        1 / 0
    except ZeroDivisionError:
        logging.getLogger("FaturaAyiklayici").exception("deneme")

    metin = yol.read_text("utf-8")
    assert "Traceback" in metin and "ZeroDivisionError" in metin


def test_bilgi_satiri_da_yazilir(yol):
    """Kök düzey WARNING'de kalır (kütüphane gürültüsü); uygulamanınki INFO."""
    main.gunluk_kur(yol)
    logging.getLogger("FaturaAyiklayici").info("koşu başladı")
    logging.getLogger("httpx").info("HTTP Request: POST gizli-adres")

    metin = yol.read_text("utf-8")
    assert "koşu başladı" in metin and "gizli-adres" not in metin


def test_yakalanmamis_thread_hatasi_yazilir(yol):
    main.gunluk_kur(yol)

    def patla():
        raise RuntimeError("thread patladı")

    t = threading.Thread(target=patla)
    t.start()
    t.join()

    assert "RuntimeError: thread patladı" in yol.read_text("utf-8")


def test_gunluk_yazilamazsa_uygulama_yine_acilir(tmp_path):
    main.gunluk_kur(tmp_path / "olmayan-klasor" / "gunluk.txt")     # hata fırlatmamalı


def test_atlanan_dosya_ve_sebebi_gunluge_yazilir(tmp_path, caplog):
    """Atlama sebebi yalnızca ekrandaydı; pencere kapanınca kayboluyordu."""
    api = Api(kok=tmp_path)
    api._log_q.put(("atlandi", {"dosya": "a.pdf", "sebep": "PDF açılamadı"}))
    api._log_q.put(("done", ([("a.pdf", "PDF açılamadı")], 0, [])))

    api._pompa_dongusu()

    assert "a.pdf" in caplog.text and "PDF açılamadı" in caplog.text


def test_elogo_hatasinin_metni_gunluge_yazilmaz(tmp_path, caplog):
    """İstisna metni token ya da yanıt gövdesi taşıyabilir: ekrana olduğu gibi
    günlüğe de yalnızca tip adı ve hatanın geçtiği satırlar gider."""
    def giris():
        raise RuntimeError("gizli-" + "token")     # kaynak satırı ize girer; bitişik yazma

    indir(["GIB2024000000001"], [], str(tmp_path), giris, queue.Queue(), threading.Event())

    assert "RuntimeError" in caplog.text and "gizli-token" not in caplog.text
