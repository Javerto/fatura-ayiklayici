import json
import queue
import threading

import pytest

from elogo_indir import indir, numaralari_ayristir, oturum_coz
from hatalar import ElogoHatasi


def olaylar(q):
    sonuc = []
    while not q.empty():
        sonuc.append(q.get_nowait())
    return sonuc


def test_numaralar_satir_bazli_tekil_ve_uzunluk():
    assert numaralari_ayristir(" AB\nab\n12345678901234567\n ") == (
        ["AB"], ["12345678901234567"])


def test_oturum_coz_gercek_sekil():
    customer = "12345678-1234-1234-1234-123456789012"
    ham = json.dumps({"access_token": "gizli", "expires_at": 12,
                      "profile": {"assignedCustomers": json.dumps({"CustomerId": customer})}})
    assert oturum_coz(ham) == ("gizli", customer, 12)


def test_oturum_token_yoksa_none():
    assert oturum_coz('{"profile": {}}') is None


def test_oturum_bozuk_musteri_hata():
    with pytest.raises(ElogoHatasi):
        oturum_coz(json.dumps({"access_token": "t", "profile": {"assignedCustomers": "[]"}}))


def test_gecerli_numara_yoksa_istemci_acilmaz(tmp_path):
    alindi = []
    q = queue.Queue()
    sonuc = indir([], ["çok-uzun"], str(tmp_path), lambda: alindi.append(1), q, threading.Event())
    assert not alindi and sonuc["gecersiz"] == ["çok-uzun"]
    assert olaylar(q)[-1][0] == "elogo_ozet"


def test_bulunamayan_numara_ozete_girer(tmp_path):
    class Istemci:
        def fatura_bul(self, nolar): return {"A": []}
    q = queue.Queue()
    sonuc = indir(["A"], [], str(tmp_path), lambda: Istemci(), q, threading.Event())
    assert sonuc["bulunamayan"] == ["A"]
    assert olaylar(q)[-1][0] == "elogo_ozet"


def test_beklenmeyen_hatada_terminal_ozet(tmp_path):
    class Istemci:
        def fatura_bul(self, nolar): raise RuntimeError("gizli")
    q = queue.Queue()
    sonuc = indir(["A"], [], str(tmp_path), lambda: Istemci(), q, threading.Event())
    assert sonuc["hata"] == "RuntimeError"
    assert olaylar(q)[-1] == ("elogo_ozet", sonuc)
