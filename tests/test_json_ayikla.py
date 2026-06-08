"""_json_ayikla — model yanıtından dayanıklı JSON çıkarma."""

import pytest

from extraction import _json_ayikla, ModelHatasi


def test_duz_json():
    assert _json_ayikla('{"fatura_no": "ABC", "tutar": 100}') == {
        "fatura_no": "ABC", "tutar": 100}


def test_json_etiketli_kod_blogu():
    cevap = '```json\n{"a": 1}\n```'
    assert _json_ayikla(cevap) == {"a": 1}


def test_etiketsiz_kod_blogu():
    cevap = '```\n{"a": 1}\n```'
    assert _json_ayikla(cevap) == {"a": 1}


def test_aciklama_metni_icinde_json():
    cevap = 'İşte çıkardığım veriler:\n{"a": 1, "b": 2}\nUmarım faydalı olur.'
    assert _json_ayikla(cevap) == {"a": 1, "b": 2}


def test_kod_blogu_ve_aciklama_birlikte():
    cevap = 'Tabii, buyrun:\n```json\n{"a": 1}\n```\nBaşka bir şey lazım mı?'
    assert _json_ayikla(cevap) == {"a": 1}


def test_ic_ice_nesne():
    assert _json_ayikla('{"a": {"b": 2}}') == {"a": {"b": 2}}


def test_bastaki_sondaki_bosluk():
    assert _json_ayikla('   \n {"a": 1} \n  ') == {"a": 1}


def test_gecersiz_json_hata_firlatir():
    with pytest.raises(ModelHatasi):
        _json_ayikla("bu hiç JSON değil")


def test_bos_yanit_hata_firlatir():
    with pytest.raises(ModelHatasi):
        _json_ayikla("")


def test_json_dizisi_nesne_degil_hata_firlatir():
    # Sözlük bekleniyor; dizi gelirse geçersiz say
    with pytest.raises(ModelHatasi):
        _json_ayikla('[1, 2, 3]')
