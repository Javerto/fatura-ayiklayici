import pathlib

import pytest

import main


def test_web_listesi_klasorle_ayni():
    """Yeni web dosyası eklenirse EXE kontrolü onu da aramalı."""
    assert sorted(p.name for p in pathlib.Path("web").iterdir()) == sorted(main.WEB_DOSYALARI)


@pytest.fixture(autouse=True)
def gecici_rapor(monkeypatch, tmp_path):
    monkeypatch.setattr(main.tempfile, "tempdir", str(tmp_path))


def test_paket_tamsa_sifir():
    assert main.saglik_kontrolu() == 0
    assert main.SAGLIK_RAPORU().read_text("utf-8") == "sağlam"


def test_eksik_web_dosyasi_nedeniyle_raporlanir(monkeypatch, tmp_path):
    bos = tmp_path / "bos"
    monkeypatch.setattr(main, "web_dosyasi", lambda ad: str(bos / ad))
    assert main.saglik_kontrolu() == 1
    assert "eksik web dosyası: index.html" in main.SAGLIK_RAPORU().read_text("utf-8")


def test_winforms_yuklenemezse_raporlanir(monkeypatch):
    monkeypatch.setitem(main.sys.modules, "webview.platforms.winforms", None)
    assert main.saglik_kontrolu() == 1
    assert "WinForms" in main.SAGLIK_RAPORU().read_text("utf-8")


def test_saglik_secenegi_pencere_acmadan_cikar(monkeypatch):
    def acilmamali(*a, **k):
        pytest.fail("pencere ya da Api oluşmamalıydı")
    monkeypatch.setattr(main, "Api", acilmamali)
    monkeypatch.setattr(main.webview, "create_window", acilmamali)
    monkeypatch.setattr(main.sys, "argv", ["main.py", "--saglik"])
    with pytest.raises(SystemExit) as cikis:
        main.main()
    assert cikis.value.code == 0
