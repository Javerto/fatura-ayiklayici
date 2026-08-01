"""Model çağrısının dayanıklılık davranışı: hız sınırı, yeniden deneme,
hata sınıflandırma.

Bu testler ÖNCE mevcut `extraction.pdf_den_veri_cek`'e karşı yazıldı
(karakterizasyon testi), sonra mantık `gemini.py` dikişinin ardına taşındı.
Taşımada yalnızca aşağıdaki `_cagir` / `_sinirlayici` yardımcıları değişti;
iddialar aynı kaldı — davranışın korunduğunun kanıtı bu. Tek istisna:
`metin_uret` artık ham metin döndürüyor (tasarım kararı), o yüzden ilk testin
başarı iddiası ayrıştırılmış sözlük yerine metne bakıyor.

Zaman enjekte edilir (`SahteZaman`): merdiveni gerçek saatle sınamak 225 saniye
sürerdi, yani hiç sınanmazdı.
"""
import threading

import pytest

import gemini
from hatalar import APIKeyHatasi, InternetHatasi

UZUN_METIN = "Fatura metni. " * 20

# Gemini'nin geçersiz anahtarda döndürdüğü gerçek metin (2026-08-01'de alındı).
API_KEY_METNI = (
    "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not "
    "valid. Please pass a valid API key.', 'status': 'INVALID_ARGUMENT', "
    "'details': [{'reason': 'API_KEY_INVALID'}]}}"
)


class SahteZaman:
    """`time` modülünün yerine geçer: uyku anında geçer, saat ileri sarar."""

    def __init__(self):
        self.simdi = 1000.0
        self.uykular = []

    def sleep(self, sure):
        self.uykular.append(sure)
        self.simdi += sure

    def monotonic(self):
        return self.simdi

    def time(self):
        return self.simdi

    @property
    def toplam_uyku(self):
        return sum(self.uykular)


class SahteModeller:
    def __init__(self, sonuclar):
        # Tek eleman kalınca onu tekrarlar: "her denemede aynı hata" senaryosu.
        self._sonuclar = list(sonuclar)
        self.cagrilar = []

    def generate_content(self, **kw):
        self.cagrilar.append(kw)
        s = self._sonuclar.pop(0) if len(self._sonuclar) > 1 else self._sonuclar[0]
        if isinstance(s, Exception):
            raise s
        return type("Yanit", (), {"text": s})()


class SahteClient:
    def __init__(self, sonuclar):
        self.models = SahteModeller(sonuclar)


@pytest.fixture
def zaman():
    """Enjekte edilen saat/uyku. Yama yok: gemini bunları parametre olarak alır."""
    return SahteZaman()


def _istemci(zaman, sonuclar, iptal=None, sinirlayici=None):
    return gemini.ModelIstemcisi(
        SahteClient(sonuclar), uyu=zaman.sleep, iptal=iptal,
        # Süreç ömürlü varsayılan sınırlayıcı gerçek saatle uyur; testler
        # kendi taze örneğini verir, yoksa testler birbirinin kotasını yer.
        sinirlayici=sinirlayici or gemini.Sinirlayici(
            uyu=zaman.sleep, saat=zaman.monotonic))


def _cagir(zaman, sonuclar, iptal=None):
    """Sahte istemciyle bir model çağrısı yapar, ham yanıtı döndürür."""
    return _istemci(zaman, sonuclar, iptal).metin_uret([UZUN_METIN])


class Gecici(Exception):
    """Geçici hata taklidi — mesaj metni sınıflandırmayı belirler."""


# ── Geri çekilme merdiveni ──────────────────────────────────────────────

def test_gecici_hatada_yeniden_dener_ve_merdiveni_tirmanir(zaman):
    cevap = _cagir(zaman, [Gecici("429 RESOURCE_EXHAUSTED"),
                           Gecici("503 UNAVAILABLE"),
                           '{"fatura_no": "GIB2024000000001"}'])

    assert cevap == '{"fatura_no": "GIB2024000000001"}'
    # 1. hatadan sonra 15 sn, 2. hatadan sonra 30 sn — saniye saniye uyunur
    assert zaman.toplam_uyku == 45
    assert zaman.uykular == [1] * 45


def test_yanittaki_retry_suresi_merdivenin_yerine_gecer(zaman):
    _cagir(zaman, [Gecici("429 quota exceeded, please retry in 42s"), "{}"])

    # Merdivenin 15'i değil, sunucunun söylediği 42 + 2 sn emniyet payı
    assert zaman.toplam_uyku == 44


def test_denemeler_tukenince_kota_mesajiyla_biter(zaman):
    with pytest.raises(InternetHatasi) as e:
        _cagir(zaman, [Gecici("429 RESOURCE_EXHAUSTED")])

    assert "istek limiti" in str(e.value)
    # 5 deneme, her birinin ardından bir bekleme: 15+30+45+60+75
    # (son deneme de bekliyor — bu mevcut davranış, testin çivilediği şey bu)
    assert zaman.toplam_uyku == 225


def test_baglanti_hatasi_tukenince_internet_mesajiyla_biter(zaman):
    with pytest.raises(InternetHatasi) as e:
        _cagir(zaman, [Gecici("Read timeout on connection")])

    assert "İnternet bağlantısı" in str(e.value)


def test_bekleme_mesaji_arayuze_gider(zaman):
    """Uzun beklemede kullanıcı ekranın donduğunu sanmamalı."""
    mesajlar = []
    gemini.ModelIstemcisi(
        SahteClient([Gecici("503 UNAVAILABLE"), "{}"]),
        uyu=zaman.sleep, bilgi=mesajlar.append,
        sinirlayici=gemini.Sinirlayici(uyu=zaman.sleep, saat=zaman.monotonic),
    ).metin_uret([UZUN_METIN])

    assert mesajlar == ["   ↻ Bağlantı hatası, 15s bekleniyor (deneme 1/5)..."]


# ── Hata sınıflandırması ────────────────────────────────────────────────

def test_api_key_hatasi_hic_yeniden_denenmez(zaman):
    client = SahteClient([Gecici(API_KEY_METNI)])
    istemci = gemini.ModelIstemcisi(
        client, uyu=zaman.sleep,
        sinirlayici=gemini.Sinirlayici(uyu=zaman.sleep, saat=zaman.monotonic))

    with pytest.raises(APIKeyHatasi) as e:
        istemci.metin_uret([UZUN_METIN])

    assert "aistudio.google.com" in str(e.value)
    assert zaman.uykular == []                  # hiç beklemedi
    assert len(client.models.cagrilar) == 1     # tek deneme


def test_taninmayan_hata_yutulmaz_ham_cikar(zaman):
    """Sınıflandırılamayan hata sessizce 'atlandı'ya dönüşmemeli."""
    with pytest.raises(Gecici):
        _cagir(zaman, [Gecici("beklenmedik bir durum")])

    assert zaman.uykular == []                  # tekrar denemeye değmez sayıldı


# ── İptal ───────────────────────────────────────────────────────────────

def test_uykunun_ortasinda_durdurma_beklemeyi_keser(zaman):
    """'Durdur'a basan kullanıcı 60 saniyelik beklemenin bitmesini beklemez."""
    iptal = threading.Event()
    gercek_sleep = zaman.sleep

    def uyu(sure):
        gercek_sleep(sure)
        if len(zaman.uykular) == 3:
            iptal.set()

    zaman.sleep = uyu

    with pytest.raises(InternetHatasi) as e:
        _cagir(zaman, [Gecici("503 UNAVAILABLE")], iptal=iptal)

    assert "durduruldu" in str(e.value)
    assert len(zaman.uykular) == 3              # 15 değil


def test_durdurulmus_islem_istek_bile_gondermez(zaman):
    iptal = threading.Event()
    iptal.set()
    client = SahteClient(["{}"])

    with pytest.raises(InternetHatasi):
        _istemci(zaman, ["{}"], iptal=iptal).metin_uret([UZUN_METIN])

    assert client.models.cagrilar == []


# ── Hız sınırlayıcı ─────────────────────────────────────────────────────

def _sinirlayici(zaman, limit=3):
    return gemini.Sinirlayici(limit=limit, uyu=zaman.sleep, saat=zaman.monotonic)


def test_limit_altinda_beklemez(zaman):
    s = _sinirlayici(zaman)

    for _ in range(3):
        s.bekle()

    assert zaman.uykular == []


def test_limit_dolunca_pencere_kayana_kadar_bekler(zaman):
    s = _sinirlayici(zaman)

    for _ in range(3):
        s.bekle()
    s.bekle()                       # 4. istek: en eski isteğin 60 sn'si dolmalı

    assert zaman.toplam_uyku == pytest.approx(60.1)


def test_pencere_kaydiktan_sonra_yeniden_akar(zaman):
    s = _sinirlayici(zaman)

    for _ in range(3):
        s.bekle()
    zaman.simdi += 61               # bir dakika geçti
    for _ in range(3):              # eski kayıtlar düştü, yeniden 3 hak
        s.bekle()

    assert zaman.uykular == []


def test_sinirlayici_calismalar_arasinda_hatirlar():
    """Kota API anahtarına ait: durdurup yeniden başlatmak sayacı sıfırlamaz.

    Bu yüzden varsayılan sınırlayıcı modül düzeyinde, süreç ömürlü duruyor.
    """
    assert gemini._VARSAYILAN_SINIRLAYICI is gemini.ModelIstemcisi(
        SahteClient(["{}"]))._sinir
