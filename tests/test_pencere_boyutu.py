"""Kayıtlı pencere boyutunun okunması."""
import pytest

import api


@pytest.fixture
def temiz_env(monkeypatch):
    monkeypatch.delenv("PENCERE", raising=False)
    return monkeypatch


def test_kayit_yoksa_varsayilan(temiz_env):
    assert api.pencere_boyutu() == api.VARSAYILAN_BOYUT


@pytest.mark.parametrize("deger", ["1200x900", "1200X900"])
def test_gecerli_kayit_okunur(temiz_env, deger):
    temiz_env.setenv("PENCERE", deger)
    assert api.pencere_boyutu() == (1200, 900)


@pytest.mark.parametrize("bozuk", ["", "abc", "1200", "1200x", "x900", "1200x900x3"])
def test_bozuk_kayit_varsayilana_duser(temiz_env, bozuk):
    temiz_env.setenv("PENCERE", bozuk)
    assert api.pencere_boyutu() == api.VARSAYILAN_BOYUT


@pytest.mark.parametrize("deger", ["100x80", "999999x900", "1200x50"])
def test_makul_disi_boyut_varsayilana_duser(temiz_env, deger):
    """Pencereyi kullanılamaz hâlde açacak kayıtlar yok sayılır."""
    temiz_env.setenv("PENCERE", deger)
    assert api.pencere_boyutu() == api.VARSAYILAN_BOYUT
