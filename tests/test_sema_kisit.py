"""Şemanın kod sahibi sütunlarla ve öğrenen kurallarla sınırları (inceleme bulguları)."""
import pytest

import sema


def _ekli(**alan):
    ham = sema.VARSAYILAN.json()
    ham["alanlar"].append({"tip": "metin", **alan})
    return ham


@pytest.mark.parametrize("etiket", ["Kaynak!", "Dosya Yolu Gizli", "Ft Formul"])
def test_turetilen_anahtar_sistem_anahtariyla_cakismaz(etiket):
    s = sema.coz(_ekli(etiket=etiket))
    sistem = {a.anahtar for a in sema.SISTEM_ALANLARI}
    assert s.alanlar[-1].anahtar not in sistem
    # Sistem anahtarı tekrar etmez: _Sema sayfasına çift yazılmaz.
    anahtarlar = [a.anahtar for a in s.tum_alanlar]
    assert len(anahtarlar) == len(set(anahtarlar))


def test_dosyada_yazili_sistem_anahtari_reddedilir():
    with pytest.raises(ValueError):
        sema.coz(_ekli(anahtar="kaynak", etiket="Menşe"))


@pytest.mark.parametrize("etiket", ["Kaynak", " dosya ", "F+T", "Vergi Tutarı"])
def test_etiket_sistem_basligiyla_ayni_olamaz(etiket):
    with pytest.raises(ValueError, match="sistem"):
        sema.coz(_ekli(etiket=etiket))


# ── "Firma için hatırla" (ogrenilir) ──
# fatura_no öğrenilirse firmanın her faturası aynı numarayı alır; tarih/sayı
# değeri kurallar JSON'una yazılamaz (TypeError).

def _ogrenilir(anahtar, deger=True):
    ham = sema.VARSAYILAN.json()
    for a in ham["alanlar"]:
        if a["anahtar"] == anahtar:
            a["ogrenilir"] = deger
    return ham


@pytest.mark.parametrize("anahtar", ["fatura_no", "fatura_tarihi", "vkn",
                                     "para_birimi", "vergiler_dahil_tutar",
                                     "toplam_miktar", "sira_no"])
def test_cekirdek_ve_metin_disi_alan_ogrenilemez(anahtar):
    with pytest.raises(ValueError, match="hatırla"):
        sema.coz(_ogrenilir(anahtar))


@pytest.mark.parametrize("tip", ["tarih", "sayi"])
def test_metin_disi_kullanici_alani_ogrenilemez(tip):
    with pytest.raises(ValueError, match="hatırla"):
        sema.coz(_ekli(etiket="Teslim", tip=tip, ogrenilir=True))


def test_firma_sabit_metin_alanlari_ogrenilir_ve_kapatilabilir():
    s = sema.coz(_ekli(etiket="Banka", ogrenilir=True))
    assert s.ogrenilen == ["sirket_adi", "vergi_dairesi", "banka"]
    assert "sirket_adi" not in sema.coz(_ogrenilir("sirket_adi", False)).ogrenilen


def test_editor_kutunun_kilidini_python_dan_alir(tmp_path):
    from api import Api
    alanlar = {a["anahtar"]: a for a in Api(kok=tmp_path).sema_oku()["alanlar"]}
    assert alanlar["sirket_adi"]["ogrenilebilir"] is True
    assert alanlar["vergi_dairesi"]["ogrenilebilir"] is True
    assert alanlar["fatura_no"]["ogrenilebilir"] is False
    assert alanlar["fatura_tarihi"]["ogrenilebilir"] is False


def test_editorden_gelen_yasak_ogrenilir_reddedilir(tmp_path):
    from api import Api
    api = Api(kok=tmp_path)
    alanlar = api.sema_oku()["alanlar"]
    alanlar[0]["ogrenilir"] = True                  # fatura_no
    once = (tmp_path / "alanlar.json").read_text("utf-8")

    assert "hata" in api.sema_kaydet(alanlar)
    assert (tmp_path / "alanlar.json").read_text("utf-8") == once
