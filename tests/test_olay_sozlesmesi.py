"""Python ile arayüz arasındaki olay sözleşmesi.

Bu anahtarları `web/app.js` ve `web/review.js` okuyor. Python tarafında biri
yeniden adlandırılırsa ekran sessizce boşalır — hiçbir davranış testi kırılmaz,
çünkü JS bu paketten çalışmıyor. Testler o yüzden anahtar adlarını sabitliyor.
"""
import pathlib
import queue
import re
import threading

import pytest

from api import Api


def _worker_olaylari(tmp_path, monkeypatch):
    import google.genai
    import worker as worker_modulu

    monkeypatch.setattr(google.genai, "Client", lambda **k: object())
    kaynak = pathlib.Path("tests/fixtures/ornek_fatura.xml").read_text("utf-8")
    (tmp_path / "f0.xml").write_text(kaynak, "utf-8")

    log_q = queue.Queue()
    worker_modulu.worker("ANAHTAR", str(tmp_path), "cikti.xlsx",
                         log_q, threading.Event())
    olaylar = []
    while not log_q.empty():
        olaylar.append(log_q.get_nowait())
    return olaylar


def test_fatura_olayinin_anahtarlari(tmp_path, monkeypatch):
    """web/app.js `olaylar()` → case "fatura" bu alanları kullanıyor."""
    olaylar = _worker_olaylari(tmp_path, monkeypatch)
    fatura = next(d for t, d in olaylar if t == "fatura")
    assert set(fatura) == {"dosya", "fatura_no", "sirket_adi", "tutar",
                           "para_birimi", "kaynak", "uyarilar", "sure"}


def test_worker_olay_tipleri(tmp_path, monkeypatch):
    """Arayüzün tanıdığı tipler; yenisi eklenebilir, mevcutlar kalmalı."""
    tipler = {t for t, _ in _worker_olaylari(tmp_path, monkeypatch)}
    assert {"progress", "isleniyor", "fatura", "review"} <= tipler


def test_review_olayinin_anahtarlari(tmp_path):
    """web/review.js `reviewAc(o)` bu alanları okuyor."""
    api = Api(kok=tmp_path)
    olay = api._review_olayi({
        "mevcut": [], "atlanmis": [], "cikti": "x.xlsx", "kesildi": False,
        "yeni": [{"fatura_no": "GIB2024000000101", "dosya_yolu": r"C:\x\a.pdf"}],
    })
    assert set(olay) == {"t", "satirlar", "alanlar", "mevcut_sayi",
                         "kesildi", "atlanan"}
    assert set(olay["satirlar"][0]) == {"i", "form", "uyarilar", "dosya",
                                        "pdf", "kaynak"}


def test_bitti_olayinin_anahtarlari(tmp_path):
    """web/app.js `bitti(o)` bu alanları okuyor."""
    api = Api(kok=tmp_path)
    api._review = {"mevcut": [], "yeni": [{"fatura_no": "A"}],
                   "atlanmis": [], "cikti": str(tmp_path / "f.xlsx")}
    sonuc = api.review_onayla({}, [0], [])      # tümü hariç → dokunulmadı dalı
    assert {"ok", "yazilan", "cikti"} <= set(sonuc)


def test_main_pencereyi_genel_nitelige_atamaz():
    """`api.pencere = ...` uygulamayı açılışta dondurur (pywebview API
    nesnesinin genel niteliklerine özyineleyerek girer). test_api.py bunu
    yakalayamıyor çünkü atama Api.__init__'te değil main.py'de yapılıyor."""
    kaynak = pathlib.Path("main.py").read_text("utf-8")
    atamalar = re.findall(r"^\s*api\.([A-Za-z]\w*)\s*=", kaynak, re.MULTILINE)
    assert not atamalar, (
        f"main.py'de '_' öneksiz nitelik ataması: {atamalar} — "
        "pywebview bunlara özyineleyerek girer ve uygulama donar")
