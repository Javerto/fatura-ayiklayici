"""Editördeki "Dene": tek fatura, aktif (kayıtlı) şemayla, Excel'e yazmadan.

Sahte, `genai.Client`'ın yerine geçer — bir katman aşağıda: böylece gerçek
`gemini.olustur` + `ModelIstemcisi` çalışır ve hem süreç ömürlü hız
sınırlayıcının sayması hem de API key hatasının Türkçe sınıflandırması
gerçek koddan geçer. Ağa çıkılmaz.
"""
import json
import threading
import types

import pytest

import gemini
import sema
from api import Api
from tests.test_worker import _pdf_olustur

YANIT = json.dumps({"fatura_no": "ABC2024000000001", "sirket_adi": "Deneme A.Ş.",
                    "vergiler_dahil_tutar": "1.200,00", "siparis_no": "SP-77"})


class SahteClient:
    """genai.Client yerine; `models.generate_content` çağrılarını sayar."""

    def __init__(self, *yanitlar):
        self._yanitlar = list(yanitlar) or [YANIT]
        self.cagrilar = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.cagrilar.append(contents)
        y = self._yanitlar.pop(0) if len(self._yanitlar) > 1 else self._yanitlar[0]
        if callable(y):
            y = y()
        if isinstance(y, Exception):
            raise y
        return types.SimpleNamespace(text=y)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sahte-key")
    sinir = gemini.Sinirlayici(uyu=lambda s: pytest.fail("bekletmemeli"))
    monkeypatch.setattr(gemini, "_VARSAYILAN_SINIRLAYICI", sinir)
    client = SahteClient()
    monkeypatch.setattr(gemini.genai, "Client", lambda **kw: client)
    pdf = tmp_path / "fatura.pdf"
    _pdf_olustur(pdf)
    return types.SimpleNamespace(api=Api(kok=tmp_path), client=client,
                                 sinir=sinir, pdf=str(pdf), kok=tmp_path)


def _siparis_alanli_sema(kok):
    ham = sema.VARSAYILAN.json()
    ham["alanlar"].append({"etiket": "Sipariş No", "tip": "metin",
                           "aciklama": "faturadaki sipariş numarası"})
    sema.yaz(kok / "alanlar.json", sema.coz(ham))


def test_dene_kayitli_semayla_tek_cagri_yapip_alanlari_dondurur(ortam):
    _siparis_alanli_sema(ortam.kok)

    o = ortam.api.dene(ortam.pdf)

    assert "hata" not in o, o
    # web/editor.js `edDene` bu anahtarları okuyor
    assert set(o) == {"dosya", "kaynak", "alanlar", "uyarilar"}
    degerler = {anahtar: deger for anahtar, _, deger in o["alanlar"]}
    assert degerler["fatura_no"] == "ABC2024000000001"
    assert degerler["vergiler_dahil_tutar"] == "1200"
    assert degerler["siparis_no"] == "SP-77"       # kayıtlı şemadaki kullanıcı alanı
    etiketler = [e for _, e, _ in o["alanlar"]]
    assert "Sipariş No" in etiketler
    assert o["dosya"] == "fatura.pdf"
    assert len(ortam.client.cagrilar) == 1
    assert "sipariş numarası" in ortam.client.cagrilar[0][0]   # prompt kayıtlı şemadan


def test_bozuk_semayla_deneme_yapilmaz(ortam):
    """`basla` gibi: bozuk dosyada sessizce tohumla denemek, kullanıcıya
    kendi alanlarının çalıştığını sandırır."""
    yol = ortam.kok / "alanlar.json"
    yol.write_text("{bozuk", "utf-8")

    o = ortam.api.dene(ortam.pdf)

    assert str(yol) in o["hata"] and o.get("sema_hatasi") is True
    assert ortam.client.cagrilar == []
    assert not ortam.api._deneniyor


def test_dene_excele_ve_gecmise_yazmaz(ortam):
    once = {p.name for p in ortam.kok.iterdir()}

    ortam.api.dene(ortam.pdf)

    assert {p.name for p in ortam.kok.iterdir()} == once
    assert not list(ortam.kok.glob("*.xlsx"))
    assert not (ortam.kok / "gecmis.json").exists()


def test_deneme_surec_omurlu_sinirlayicida_sayilir(ortam):
    """Kota API anahtarına aittir: deneme de sayılmazsa ardından başlayan
    koşu dakikalık limiti aşar ve 429 yer."""
    ortam.api.dene(ortam.pdf)
    assert len(ortam.sinir._zamanlar) == 1


def test_gecersiz_api_key_turkce_mesajla_doner(ortam):
    # Google'ın gerçek hata metni (tests/test_gemini.py ile aynı imza)
    ortam.client._yanitlar = [Exception(
        "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key. "
        "reason: API_KEY_INVALID")]
    o = ortam.api.dene(ortam.pdf)
    assert "API key geçersiz" in o["hata"]


def test_api_key_yoksa_arayuze_api_key_isareti_doner(ortam, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert ortam.api.dene(ortam.pdf) == {"hata": "api_key"}
    assert ortam.client.cagrilar == []


def test_cozulemeyen_model_yaniti_turkce_mesajla_doner(ortam):
    ortam.client._yanitlar = ["Üzgünüm, bu faturayı okuyamadım."]
    o = ortam.api.dene(ortam.pdf)
    assert o["hata"].startswith("Model")


def test_beklenmedik_hata_arayuze_kacmaz(ortam):
    ortam.client._yanitlar = [Exception("400 INVALID_ARGUMENT tuhaf bir şey")]
    o = ortam.api.dene(ortam.pdf)
    assert "Beklenmedik hata" in o["hata"]


def test_iptal_edilen_deneme_turkce_mesajla_doner(ortam):
    """Kullanıcı Durdur'a bastıysa yeniden denenmez, mesaj Türkçe döner."""
    def iptal_ve_gecici_hata():
        ortam.api.durdur()
        return Exception("503 UNAVAILABLE")
    ortam.client._yanitlar = [iptal_ve_gecici_hata]
    o = ortam.api.dene(ortam.pdf)
    assert o["hata"] == "Deneme durduruldu."
    assert len(ortam.client.cagrilar) == 1          # geri çekilmede yeniden denenmedi


def _asili_deneme(ortam):
    """Model çağrısında bekleyen bir deneme başlatır; (thread, bırak) döner."""
    icerde, birak = threading.Event(), threading.Event()

    def bekle():
        icerde.set()
        assert birak.wait(5)
        return YANIT
    ortam.client._yanitlar = [bekle]
    t = threading.Thread(target=ortam.api.dene, args=(ortam.pdf,))
    t.start()
    assert icerde.wait(5)
    return t, birak


def test_deneme_surerken_ikinci_deneme_reddedilir(ortam):
    t, birak = _asili_deneme(ortam)
    try:
        assert "hata" in ortam.api.dene(ortam.pdf)
    finally:
        birak.set()
        t.join(5)
    assert len(ortam.client.cagrilar) == 1
    assert "hata" not in ortam.api.dene(ortam.pdf)     # bittikten sonra serbest


def test_deneme_surerken_kosu_baslatilamaz(ortam):
    t, birak = _asili_deneme(ortam)
    try:
        assert "hata" in ortam.api.basla({"klasor": str(ortam.kok)})
    finally:
        birak.set()
        t.join(5)
    assert len(ortam.client.cagrilar) == 1


def test_kosu_surerken_deneme_reddedilir(ortam):
    ortam.api._calisiyor = True
    assert "hata" in ortam.api.dene(ortam.pdf)
    assert ortam.client.cagrilar == []


def test_pdf_olmayan_ya_da_olmayan_dosya_reddedilir(ortam):
    """JS bir güven sınırı: yol arayüzden gelir."""
    assert "hata" in ortam.api.dene(str(ortam.kok / "yok.pdf"))
    xml = ortam.kok / "f.xml"
    xml.write_text("<x/>", "utf-8")
    assert "hata" in ortam.api.dene(str(xml))
    assert "hata" in ortam.api.dene(None)
    assert ortam.client.cagrilar == []
