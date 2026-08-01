"""Model çağrısının dayanıklılık davranışı: hız sınırı, yeniden deneme,
hata sınıflandırma.

Bu testler ÖNCE mevcut `extraction.pdf_den_veri_cek`'e karşı yazıldı
(karakterizasyon testi). Amaç: bu mantık `gemini.py` dikişinin ardına
taşınırken davranışın birebir korunduğunu kanıtlamak. Taşımadan sonra
yalnızca aşağıdaki `_cagir` / `_sinir_cagir` yardımcıları değişir;
iddialar aynı kalır. Kırmızıya dönen her iddia = kazara değiştirilmiş davranış.

Zaman enjekte edilir (`SahteZaman`): merdiveni gerçek saatle sınamak 225 saniye
sürerdi, yani hiç sınanmazdı.
"""
import queue
import threading

import pytest

import extraction
from hatalar import APIKeyHatasi, InternetHatasi

# 100 karakterden uzun: dijital metin dalı seçilsin, fitz'e hiç dokunulmasın.
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
def zaman(monkeypatch):
    """extraction'ın gördüğü `time` adını sahteyle değiştirir.

    Adın tanımlandığı yeri değil, kullanıldığı yeri yamalıyoruz; ayrıca
    süreç-geneli `_istek_zamanlari` deque'si testler arasında sızmasın diye
    her testte temizleniyor (yoksa 14 isteklik kota testleri birbirine bağlar).
    """
    sahte = SahteZaman()
    monkeypatch.setattr(extraction, "time", sahte)
    extraction._istek_zamanlari.clear()
    yield sahte
    extraction._istek_zamanlari.clear()


def _cagir(sonuclar, iptal=None):
    """Sahte istemciyle bir model çağrısı yapar, çıkarılan satırı döndürür."""
    client = SahteClient(sonuclar)
    return extraction.pdf_den_veri_cek(
        "C:/klasor/fatura.pdf", client, queue.Queue(),
        iptal or threading.Event(), 1.5, metin=UZUN_METIN)


def _sinir_cagir(kere):
    for _ in range(kere):
        extraction._rpm_bekle()


class Gecici(Exception):
    """Geçici hata taklidi — mesaj metni sınıflandırmayı belirler."""


# ── Geri çekilme merdiveni ──────────────────────────────────────────────

def test_gecici_hatada_yeniden_dener_ve_merdiveni_tirmanir(zaman):
    veri = _cagir([Gecici("429 RESOURCE_EXHAUSTED"),
                   Gecici("503 UNAVAILABLE"),
                   '{"fatura_no": "GIB2024000000001"}'])

    assert veri["fatura_no"] == "GIB2024000000001"
    # 1. hatadan sonra 15 sn, 2. hatadan sonra 30 sn — saniye saniye uyunur
    assert zaman.toplam_uyku == 45
    assert zaman.uykular == [1] * 45


def test_yanittaki_retry_suresi_merdivenin_yerine_gecer(zaman):
    _cagir([Gecici("429 quota exceeded, please retry in 42s"), '{"fatura_no": "A"}'])

    # Merdivenin 15'i değil, sunucunun söylediği 42 + 2 sn emniyet payı
    assert zaman.toplam_uyku == 44


def test_denemeler_tukenince_kota_mesajiyla_biter(zaman):
    with pytest.raises(InternetHatasi) as e:
        _cagir([Gecici("429 RESOURCE_EXHAUSTED")])

    assert "istek limiti" in str(e.value)
    # 5 deneme, her birinin ardından bir bekleme: 15+30+45+60+75
    # (son deneme de bekliyor — bu mevcut davranış, testin çivilediği şey bu)
    assert zaman.toplam_uyku == 225


def test_baglanti_hatasi_tukenince_internet_mesajiyla_biter(zaman):
    with pytest.raises(InternetHatasi) as e:
        _cagir([Gecici("Read timeout on connection")])

    assert "İnternet bağlantısı" in str(e.value)


# ── Hata sınıflandırması ────────────────────────────────────────────────

def test_api_key_hatasi_hic_yeniden_denenmez(zaman):
    client = SahteClient([Gecici(API_KEY_METNI)])

    with pytest.raises(APIKeyHatasi) as e:
        extraction.pdf_den_veri_cek(
            "C:/klasor/fatura.pdf", client, queue.Queue(),
            threading.Event(), 1.5, metin=UZUN_METIN)

    assert "aistudio.google.com" in str(e.value)
    assert zaman.uykular == []                  # hiç beklemedi
    assert len(client.models.cagrilar) == 1     # tek deneme


def test_taninmayan_hata_yutulmaz_ham_cikar(zaman):
    """Sınıflandırılamayan hata sessizce 'atlandı'ya dönüşmemeli."""
    with pytest.raises(Gecici):
        _cagir([Gecici("beklenmedik bir durum")])

    assert zaman.uykular == []                  # tekrar denemeye değmez sayıldı


# ── İptal ───────────────────────────────────────────────────────────────

def test_uykunun_ortasinda_durdurma_beklemeyi_kesers(zaman):
    """'Durdur'a basan kullanıcı 60 saniyelik beklemenin bitmesini beklemez."""
    iptal = threading.Event()
    gercek_sleep = zaman.sleep

    def uyu(sure):
        gercek_sleep(sure)
        if len(zaman.uykular) == 3:
            iptal.set()

    zaman.sleep = uyu

    with pytest.raises(InternetHatasi) as e:
        _cagir([Gecici("503 UNAVAILABLE")], iptal=iptal)

    assert "durduruldu" in str(e.value)
    assert len(zaman.uykular) == 3              # 15 değil


def test_durdurulmus_islem_istek_bile_gondermez(zaman):
    iptal = threading.Event()
    iptal.set()
    client = SahteClient(['{"fatura_no": "A"}'])

    with pytest.raises(InternetHatasi):
        extraction.pdf_den_veri_cek(
            "C:/klasor/fatura.pdf", client, queue.Queue(), iptal, 1.5,
            metin=UZUN_METIN)

    assert client.models.cagrilar == []


# ── Hız sınırlayıcı ─────────────────────────────────────────────────────

def test_limit_altinda_beklemez(zaman, monkeypatch):
    monkeypatch.setattr(extraction, "RPM_LIMIT", 3)

    _sinir_cagir(3)

    assert zaman.uykular == []


def test_limit_dolunca_pencere_kayana_kadar_bekler(zaman, monkeypatch):
    monkeypatch.setattr(extraction, "RPM_LIMIT", 3)

    _sinir_cagir(3)
    _sinir_cagir(1)                 # 4. istek: en eski isteğin 60 sn'si dolmalı

    assert zaman.toplam_uyku == pytest.approx(60.1)


def test_pencere_kaydiktan_sonra_yeniden_akar(zaman, monkeypatch):
    monkeypatch.setattr(extraction, "RPM_LIMIT", 3)

    _sinir_cagir(3)
    zaman.simdi += 61               # bir dakika geçti
    _sinir_cagir(3)                 # eski kayıtlar düştü, yeniden 3 hak

    assert zaman.uykular == []
