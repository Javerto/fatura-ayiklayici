"""Şema editörünün Python uç noktaları: `Api.sema_oku` / `Api.sema_kaydet`.

JS bir güven sınırıdır: arayüz bu metotları her argümanla çağırabilir.
Kısıtlar (boş/yinelenen etiket, tip kilidi, çekirdek, koşu kilidi) burada
reddedilmeli, yalnızca arayüzde değil.
"""
import json

import sema
from api import Api


def _alanlar(api):
    return api.sema_oku()["alanlar"]


def test_sema_oku_tohum_alanlarini_form_sirasiyla_verir(tmp_path):
    o = Api(kok=tmp_path).sema_oku()
    assert [a["etiket"] for a in o["alanlar"]][:3] == ["Fatura No", "Fatura Tarihi", "Şirket Adı"]
    fno = o["alanlar"][0]
    assert fno["cekirdek"] is True and fno["tip"] == "metin"
    assert "sutun" not in fno          # sütun numarası arayüze hiç gitmez
    assert o["dosya_hatasi"] is None


def test_kosu_surerken_editor_acilmaz(tmp_path):
    api = Api(kok=tmp_path)
    api._calisiyor = True
    assert "hata" in api.sema_oku()


def test_bozuk_dosyanin_sebebi_editore_gelir_ve_dosyaya_dokunulmaz(tmp_path):
    """#5'ten beri bozuk alanlar.json sessizce tohuma düşüyordu; kullanıcı
    kendi alanlarının neden kaybolduğunu göremiyordu."""
    api = Api(kok=tmp_path)
    ham = sema.VARSAYILAN.json()
    ham["alanlar"][0]["etiket"] = ""
    yol = tmp_path / "alanlar.json"
    yol.write_text(json.dumps(ham), "utf-8")

    o = api.sema_oku()

    assert o["dosya_hatasi"]
    assert json.loads(yol.read_text("utf-8")) == ham


def test_kaydet_etiket_aciklama_ve_sirayi_degistirir(tmp_path):
    api = Api(kok=tmp_path)
    alanlar = _alanlar(api)
    alanlar[2]["etiket"] = "Satıcı Firma"
    alanlar[2]["aciklama"] = "satıcı"
    alanlar.insert(0, alanlar.pop(2))

    assert api.sema_kaydet(alanlar) == {"ok": True}

    s = sema.oku(tmp_path / "alanlar.json")
    assert s.alanlar[0].anahtar == "sirket_adi"
    assert s.alanlar[0].etiket == "Satıcı Firma"
    assert s.alanlar[0].aciklama == "satıcı"
    assert s.sutun["sirket_adi"] == 11          # sütun etiketle/sırayla oynamaz


def _yeni(etiket, tip="metin", **k):
    return {"etiket": etiket, "tip": tip, "aciklama": "x", **k}


def test_yeni_alan_sona_sutun_ve_slugdan_anahtar_alir(tmp_path):
    api = Api(kok=tmp_path)
    # Öğrenilir yalnızca metin alanında açılabilir (bkz. test_sema_kisit).
    alanlar = _alanlar(api) + [_yeni("Sipariş No", "metin", ogrenilir=True,
                                     zorunlu=True),
                               _yeni("Fatura-No")]     # slug "fatura_no" dolu

    assert api.sema_kaydet(alanlar) == {"ok": True}

    s = sema.oku(tmp_path / "alanlar.json")
    sip, fno2 = s.alanlar[-2], s.alanlar[-1]
    assert (sip.anahtar, sip.tip, sip.sutun) == ("siparis_no", "metin", 17)
    assert sip.ogrenilir and sip.zorunlu and sip.aktif
    assert (fno2.anahtar, fno2.sutun) == ("fatura_no_2", 18)


def test_kullanici_alani_pasife_alinir_ve_geri_acilir(tmp_path):
    api = Api(kok=tmp_path)
    api.sema_kaydet(_alanlar(api) + [_yeni("Sipariş No")])
    alanlar = _alanlar(api)
    alanlar[-1]["aktif"] = False
    alanlar[-1]["ogrenilir"] = True

    assert api.sema_kaydet(alanlar) == {"ok": True}
    son = sema.oku(tmp_path / "alanlar.json").alanlar[-1]
    assert not son.aktif and son.ogrenilir and son.sutun == 17


def _bos_etiket(a):        a[3]["etiket"] = "   "
def _yinelenen_etiket(a):  a[3]["etiket"] = " fatura no "     # büyük/küçük, boşluk
def _yeni_yinelenen(a):    a.append(_yeni("VKN"))
def _cekirdek_pasif(a):    a[0]["aktif"] = False
def _cekirdek_eksik(a):    del a[0]
def _bilinmeyen_anahtar(a): a[0]["anahtar"] = "uydurma"
def _ayni_alan_iki_kez(a): a.append(dict(a[0]))
def _bozuk_tip(a):         a.append(_yeni("Yeni", "renk"))
def _alan_nesne_degil(a):  a.append("x")
def _etiket_metin_degil(a): a[0]["etiket"] = 5


def _kullanici_tipi_degisir(a):
    a[-1]["tip"] = "sayi"


import pytest


@pytest.mark.parametrize("boz", [
    _bos_etiket, _yinelenen_etiket, _yeni_yinelenen, _cekirdek_pasif,
    _cekirdek_eksik, _bilinmeyen_anahtar, _ayni_alan_iki_kez, _bozuk_tip,
    _alan_nesne_degil, _etiket_metin_degil, _kullanici_tipi_degisir])
def test_gecersiz_kayit_reddedilir_ve_dosyaya_dokunulmaz(tmp_path, boz):
    api = Api(kok=tmp_path)
    assert api.sema_kaydet(_alanlar(api) + [_yeni("Sipariş No")]) == {"ok": True}
    yol = tmp_path / "alanlar.json"
    once = yol.read_text("utf-8")
    alanlar = _alanlar(api)
    boz(alanlar)

    sonuc = api.sema_kaydet(alanlar)

    assert "hata" in sonuc and sonuc["hata"], sonuc
    assert yol.read_text("utf-8") == once


@pytest.mark.parametrize("girdi", [None, "x", {"a": 1}, 5])
def test_liste_olmayan_girdi_reddedilir(tmp_path, girdi):
    assert "hata" in Api(kok=tmp_path).sema_kaydet(girdi)


def test_tohum_alaninin_tipi_degistirilemez(tmp_path):
    """coz tohum tipini sessizce geri zorlardı; kullanıcı kaydettiğini sanır."""
    api = Api(kok=tmp_path)
    alanlar = _alanlar(api)
    alanlar[0]["tip"] = "sayi"
    assert "hata" in api.sema_kaydet(alanlar)


def test_kosu_surerken_kaydedilmez(tmp_path):
    api = Api(kok=tmp_path)
    alanlar = _alanlar(api)
    alanlar[0]["etiket"] = "Başka"
    api._calisiyor = True
    assert "hata" in api.sema_kaydet(alanlar)
    assert sema.oku(tmp_path / "alanlar.json").alanlar[0].etiket == "Fatura No"


def test_deneme_surerken_kaydedilmez(tmp_path):
    """Dene kayıtlı şemayı okur; deneme sürerken kayıt sonucu hangi şemayla
    alındığını belirsizleştirir."""
    api = Api(kok=tmp_path)
    alanlar = _alanlar(api)
    alanlar[0]["etiket"] = "Başka"
    api._deneniyor = True
    assert "hata" in api.sema_kaydet(alanlar)
    assert sema.oku(tmp_path / "alanlar.json").alanlar[0].etiket == "Fatura No"


def test_kaydet_calisan_kosunun_semasini_degistirmez(tmp_path):
    """Gözden geçirme/onay o koşunun şemasıyla çalışır; yeni şema sonraki
    `basla`'da okunur."""
    api = Api(kok=tmp_path)
    once = api._sema
    api.sema_kaydet(_alanlar(api) + [_yeni("Sipariş No")])
    assert api._sema == once
