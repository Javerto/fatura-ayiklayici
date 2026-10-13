"""Şema/arşiv uyuşmazlık uyarısı (bilet #7).

Şema makine başına, arşiv klasör başınadır. Arşivin gömülü şeması aktif
şemadan farklıysa koşu düzeyinde uyarı çıkar; işlem durmaz.
"""
import datetime
import pathlib
import queue
import shutil
import threading

from openpyxl import load_workbook

import sema
from excel_utils import SEMA_SAYFASI, excel_olustur, sema_farki
from worker import worker


def _satir():
    return {"fatura_no": "GIB2024000000101", "sirket_adi": "ACME A.Ş.",
            "vkn": "1234567890", "vergiler_dahil_tutar": 1180.0,
            "kdv_haric_tutar": 1000.0, "para_birimi": "TRY",
            "fatura_tarihi": datetime.datetime(2024, 1, 15),
            "dosya_yolu": r"C:\x\a.pdf", "_teknik_bilgi": "Dijital"}


def _siparisli():
    ham = sema.VARSAYILAN.json()
    ham["alanlar"].append({"etiket": "Sipariş No", "tip": "metin",
                           "aciklama": "Sipariş numarası"})
    return sema.coz(ham)


def test_arsivde_olup_semada_olmayan_alan_sayilir(tmp_path):
    yol = str(tmp_path / "f.xlsx")
    excel_olustur([_satir()], yol, _siparisli())

    fark = sema_farki(yol, sema.VARSAYILAN)
    assert fark == {"arsivde_fazla": ["Sipariş No"], "yeni": []}


def test_semada_olup_arsivde_olmayan_alan_ayri_sayilir(tmp_path):
    yol = str(tmp_path / "f.xlsx")
    excel_olustur([_satir()], yol, sema.VARSAYILAN)

    fark = sema_farki(yol, _siparisli())
    assert fark == {"arsivde_fazla": [], "yeni": ["Sipariş No"]}


def test_semalar_ayniysa_uyari_yok(tmp_path):
    yol = str(tmp_path / "f.xlsx")
    excel_olustur([_satir()], yol, _siparisli())
    assert sema_farki(yol, _siparisli()) is None


def test_gomulu_semasi_olmayan_eski_arsivde_uyari_yok(tmp_path):
    yol = str(tmp_path / "f.xlsx")
    excel_olustur([_satir()], yol, _siparisli())
    wb = load_workbook(yol)
    del wb[SEMA_SAYFASI]                # bilet #4 öncesi sürümün yazdığı dosya
    wb.save(yol)
    assert sema_farki(yol, sema.VARSAYILAN) is None


def test_arsiv_yoksa_uyari_yok(tmp_path):
    assert sema_farki(str(tmp_path / "yok.xlsx"), _siparisli()) is None


def _review_yuku(klasor, aktif_sema):
    shutil.copy(pathlib.Path(__file__).parent / "fixtures" / "ornek_fatura.xml",
                klasor / "yeni.xml")
    log_q = queue.Queue()
    # XML-only akış modele gitmez; istemci yalnızca kurulmasın diye veriliyor.
    worker("ANAHTAR", str(klasor), "cikti.xlsx", log_q, threading.Event(),
           istemci=object(), sema=aktif_sema)
    olaylar = []
    while not log_q.empty():
        olaylar.append(log_q.get_nowait())
    return next(d for t, d in olaylar if t == "review")


def test_worker_uyusmazligi_review_yukune_koyar_ve_durmaz(tmp_path):
    excel_olustur([_satir()], str(tmp_path / "cikti.xlsx"), _siparisli())

    yuk = _review_yuku(tmp_path, sema.VARSAYILAN)
    assert yuk["sema_farki"] == {"arsivde_fazla": ["Sipariş No"], "yeni": []}
    assert len(yuk["yeni"]) == 1          # işlem durmadı, yeni fatura onaya geldi
    assert len(yuk["mevcut"]) == 1        # arşiv okunmaya devam etti


def test_uyusmazlik_onayi_engellemez(tmp_path):
    from api import Api

    cikti = str(tmp_path / "cikti.xlsx")
    excel_olustur([_satir()], cikti, _siparisli())
    api = Api(kok=tmp_path / "ayar")
    api._pencere = type("P", (), {"evaluate_js": lambda self, k: None})()
    api._review = _review_yuku(tmp_path, api._sema)
    assert api._review["sema_farki"]

    sonuc = api.review_onayla({}, [], [])
    assert sonuc["ok"] and sonuc["yazilan"] == 1
    # Onaylanan dosya aktif şemayla yazıldı; bir sonraki koşuda uyarı kalmaz.
    assert sema_farki(cikti, api._sema) is None


def test_worker_semalar_ayniysa_uyusmazlik_yok(tmp_path):
    excel_olustur([_satir()], str(tmp_path / "cikti.xlsx"), sema.VARSAYILAN)
    assert _review_yuku(tmp_path, sema.VARSAYILAN)["sema_farki"] is None
