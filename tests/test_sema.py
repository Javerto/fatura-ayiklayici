"""Şema dosyası (`alanlar.json`): okuma, yazma, onarım ve türetilen görünümler.

Testler gerçek `alanlar.json`'a dokunmaz; her test kendi `tmp_path`'ini verir.
"""
import json

import sema


def _ham(yol):
    return json.loads(yol.read_text("utf-8"))


def test_dosya_yoksa_tohumdan_yazilir_ve_surum_tasir(tmp_path):
    yol = tmp_path / "alanlar.json"
    s = sema.oku(yol)

    ham = _ham(yol)
    assert ham["surum"] == 1
    anahtarlar = [a["anahtar"] for a in ham["alanlar"]]
    assert anahtarlar[0] == "fatura_no"
    assert [a.anahtar for a in s.alanlar] == anahtarlar


def _yaz(yol, ham):
    yol.write_text(json.dumps(ham, ensure_ascii=False), "utf-8")


def test_sonraki_acilista_dosyadan_okunur(tmp_path):
    yol = tmp_path / "alanlar.json"
    sema.oku(yol)
    ham = _ham(yol)
    ham["alanlar"][2]["etiket"] = "Satıcı Firma"
    _yaz(yol, ham)

    s = sema.oku(yol)
    assert ("sirket_adi", "Satıcı Firma", "metin") in s.duzenlenebilir


def test_dosya_silinince_yeniden_dogar(tmp_path):
    yol = tmp_path / "alanlar.json"
    sema.oku(yol)
    yol.unlink()
    assert sema.oku(yol) == sema.VARSAYILAN
    assert yol.exists()


def test_bozuk_dosyada_cokmez_ve_dosyaya_dokunmaz(tmp_path):
    """Bozuk dosya kullanıcının elle yazdığı tanımları taşıyor olabilir; üzerine
    tohum yazmak onları sessizce yok eder. Uygulama tohumla çalışmaya devam eder."""
    yol = tmp_path / "alanlar.json"
    for icerik in ('{"alanlar": [', '[]', '{"surum": 1}',
                   '{"surum": 1, "alanlar": [{"etiket": ""}]}',
                   '{"surum": 1, "alanlar": [{"etiket": "X", "tip": "renk"}]}',
                   '{"surum": 1, "alanlar": [{"etiket": "X", "tip": "metin", "sutun": 5}]}',
                   '{"surum": 1, "alanlar": [{"etiket": "X", "tip": "metin", "sutun": "a"}]}'):
        yol.write_text(icerik, "utf-8")
        assert sema.oku(yol) == sema.VARSAYILAN, icerik
        assert yol.read_text("utf-8") == icerik


def test_elle_eklenen_alan_anahtar_ve_sona_sutun_alir_ve_kalici_olur(tmp_path):
    """Kullanıcı yalnızca etiket/tip/açıklama yazar; anahtar ve sütun sistemin.
    Atanan değerler dosyaya geri yazılır — yoksa bir sonraki elle ekleme aynı
    sütunu başka alana verip arşivi kaydırırdı."""
    yol = tmp_path / "alanlar.json"
    sema.oku(yol)
    ham = _ham(yol)
    ham["alanlar"].append({"etiket": "Sipariş No", "tip": "metin",
                           "aciklama": "alıcının sipariş numarası"})
    _yaz(yol, ham)

    s = sema.oku(yol)
    yeni = s.alanlar[-1]
    assert (yeni.anahtar, yeni.sutun, yeni.aktif) == ("siparis_no", 17, True)
    assert _ham(yol)["alanlar"][-1]["anahtar"] == "siparis_no"
    assert _ham(yol)["alanlar"][-1]["sutun"] == 17

    # Bir sonraki elle ekleme bir sonraki sütunu alır; öncekininki değişmez.
    ham = _ham(yol)
    # Etiket farklı (aynı etiket yasak), slug aynı → sona sayı eklenir.
    ham["alanlar"].insert(0, {"etiket": "Sipariş-No", "tip": "tarih"})
    _yaz(yol, ham)
    s = sema.oku(yol)
    assert s.sutun["siparis_no"] == 17
    assert (s.alanlar[0].anahtar, s.alanlar[0].sutun) == ("siparis_no_2", 18)


def test_tohum_alani_dosyadan_silinse_de_geri_gelir(tmp_path):
    """Kod tohum alanlarına (formüller, doğrulama) adıyla dayanıyor; dosyadan
    silinmiş bir tohum alanı çökme demek. Kalıcı silme kapsam dışı — geri eklenir,
    sütunu ve tipi tohumdakidir."""
    yol = tmp_path / "alanlar.json"
    sema.oku(yol)
    ham = _ham(yol)
    ham["alanlar"] = [a for a in ham["alanlar"] if a["anahtar"] != "kdv_haric_tutar"]
    ham["alanlar"][0]["tip"] = "sayi"           # fatura_no'nun tipi kilitli
    _yaz(yol, ham)

    s = sema.oku(yol)
    assert s.sutun["kdv_haric_tutar"] == 9
    assert s.tip_haritasi["kdv_haric_tutar"] == "sayi"
    assert s.tip_haritasi["fatura_no"] == "metin"
    assert any(a["anahtar"] == "kdv_haric_tutar" for a in _ham(yol)["alanlar"])


def test_yazma_atomik_yarim_kalan_yazim_eski_dosyayi_bozmaz(tmp_path, monkeypatch):
    yol = tmp_path / "alanlar.json"
    sema.oku(yol)
    once = yol.read_text("utf-8")

    def patla(*_):
        raise OSError("disk dolu")
    monkeypatch.setattr(sema.os, "replace", patla)
    try:
        sema.yaz(yol, sema.VARSAYILAN)
    except OSError:
        pass
    assert yol.read_text("utf-8") == once
    assert not (tmp_path / "alanlar.json.tmp").exists()


def test_surum_okunur_ve_bilinmeyen_surum_reddedilir(tmp_path):
    """Sürüm, biçim değişirse eski dosyayı tanımak için. Daha yeni bir sürümün
    dosyasını anlamadan okuyup geri yazmak onu bozar."""
    yol = tmp_path / "alanlar.json"
    sema.oku(yol)
    ham = _ham(yol)
    ham["surum"] = 99
    ham["alanlar"][0]["etiket"] = "Değişti"
    _yaz(yol, ham)
    assert sema.oku(yol) == sema.VARSAYILAN
    assert _ham(yol)["surum"] == 99
