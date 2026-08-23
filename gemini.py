"""Gemini adaptörü — model çağrısının tek kapısı.

Çağıran taraf yalnızca şunu bilir:

    istemci.metin_uret(parcalar) -> str

Ardında hız sınırlama, yeniden deneme ve hata sınıflandırma durur; `extraction`
ve `worker` bunların hiçbirini görmez ve `google.genai`'yi hiç import etmez.
Dikişin varlık sebebi test edilebilirlik: sahte bir istemciyle "3. denemede
429, sonra başarı" gibi senaryolar milisaniyede sınanabiliyor.

`parcalar` listesi `str` (metin) ve `bytes` (JPEG görsel) öğelerinden oluşur;
Gemini'nin `Part` tipi bu modülün dışına çıkmaz.

Uyku (`uyu`) ve saat (`saat`) dışarıdan verilebilir: geri çekilme merdivenini
gerçek saatle sınamak 225 saniye sürerdi, yani hiç sınanmazdı.
"""

import os
import re
import threading
import time
from collections import deque

import google.genai as genai
from google.genai import types

from hatalar import APIKeyHatasi, InternetHatasi

# ─── AYARLAR ─────────────────────────────────────────────────────────────────
# Varsayılan model. FA_MODEL ortam değişkeni yalnızca altın küme A/B'si için:
# `FA_MODEL=gemini-3.5-flash-lite python altin.py` ile aynı küme başka bir
# modele koşulur, kod değiştirilip geri alınmaz. Varsayılanı değiştirmek
# ölçüm sonrası bilinçli bir karardır.
GEMMA_MODEL     = os.getenv("FA_MODEL", "gemma-4-31b-it")   # 2026-08-01'de models.list() ile doğrulandı
MAX_DENEME      = 5
TIMEOUT_SANIYE  = 180
THINKING_BUDGET = -1
RPM_LIMIT       = 14   # dakikada max istek (limitin biraz altında güvenli taraf)
# ─────────────────────────────────────────────────────────────────────────────

# Geçici sayılan (yeniden denenen) ve kalıcı sayılan hata imzaları. Sağlayıcı
# yapılandırılmış bir hata kodu vermediği için eşleme hata METNİ üzerinden;
# tests/test_gemini.py bu sınıflandırmayı gerçek Google yanıtlarına karşı çiviler.
TEKRAR_HATALARI  = ("429", "resource_exhausted", "503", "504", "unavailable",
                    "deadline_exceeded", "ssl", "timeout", "readtimeout",
                    "connecttimeout", "connectionerror", "remoteprotocolerror", "recv")
API_KEY_HATALARI = ("api_key_invalid", "api key", "invalid_api_key",
                    "permission_denied", "unauthenticated")

if THINKING_BUDGET == 0:
    _GEN_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0))
elif THINKING_BUDGET > 0:
    _GEN_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET))
else:
    _GEN_CONFIG = None


class Sinirlayici:
    """Dakikada `limit` isteği aşmamak için gerekirse bekletir.

    Durumu SÜREÇ ömürlüdür, çalışma ömürlü değil: kota API anahtarına aittir.
    Kullanıcı 14 fatura işleyip durdurup hemen yeniden başlatırsa sayaç
    sıfırlanmamalı, yoksa ikinci çalışma anında 429 yer.
    """

    def __init__(self, limit: int = RPM_LIMIT, uyu=time.sleep, saat=time.monotonic):
        self._limit = limit
        self._uyu = uyu
        self._saat = saat
        self._kilit = threading.Lock()
        self._zamanlar: deque = deque()   # son 60 saniyedeki istek zamanları

    def bekle(self):
        while True:
            with self._kilit:
                simdi = self._saat()
                while self._zamanlar and simdi - self._zamanlar[0] >= 60:
                    self._zamanlar.popleft()
                if len(self._zamanlar) < self._limit:
                    self._zamanlar.append(simdi)
                    return
                # En eski isteğin 60 saniyesi dolana kadar beklenecek süre
                sure = 60 - (simdi - self._zamanlar[0]) + 0.1
            self._uyu(sure)


# Süreç ömürlü varsayılan: her çalışma yeni bir istemci kursa da kota sayacı aynı.
_VARSAYILAN_SINIRLAYICI = Sinirlayici()


class ModelIstemcisi:
    """Model çağrısı: hız sınırı · yeniden deneme · hata sınıflandırma."""

    def __init__(self, client, *, bilgi=None, iptal=None,
                 uyu=time.sleep, sinirlayici: Sinirlayici | None = None):
        self._client = client
        # `bilgi` arayüze bekleme mesajı geçirir; kuyruk/olay etiketi bilgisi
        # çağıranda kalsın diye kuyruk değil, düz bir fonksiyon alıyoruz.
        self._bilgi = bilgi or (lambda mesaj: None)
        self._iptal = iptal or threading.Event()
        self._uyu = uyu
        self._sinir = sinirlayici if sinirlayici is not None else _VARSAYILAN_SINIRLAYICI

    def metin_uret(self, parcalar) -> str:
        """Modelden ham metin yanıtı alır.

        parcalar: `str` (metin) ve `bytes` (JPEG görsel) öğelerinden liste.
        Geçici hatalarda yeniden dener; kalıcı hatayı sınıflandırıp fırlatır.
        """
        icerik = [types.Part.from_bytes(data=p, mime_type="image/jpeg")
                  if isinstance(p, bytes) else p for p in parcalar]

        son_hata = None
        for deneme in range(MAX_DENEME):
            self._sinir.bekle()
            self._iptal_kontrol()
            try:
                yanit = self._client.models.generate_content(
                    model=GEMMA_MODEL, contents=icerik, config=_GEN_CONFIG)
                return yanit.text
            except Exception as e:
                hata_metni = str(e).lower()
                if any(k in hata_metni for k in API_KEY_HATALARI):
                    raise APIKeyHatasi(
                        "API key geçersiz veya süresi dolmuş.\n"
                        "Lütfen geçerli bir key girin (aistudio.google.com).")
                son_hata = e
                if not any(k in hata_metni for k in TEKRAR_HATALARI):
                    break
                self._geri_cekil(deneme, e)

        raise self._siniflandir(son_hata)

    # ── İç yardımcılar ───────────────────────────────────────────────────

    def _iptal_kontrol(self):
        if self._iptal.is_set():
            raise InternetHatasi("İşlem durduruldu.")

    def _geri_cekil(self, deneme: int, hata: Exception):
        """Merdiven: 15/30/45/60/75 sn. Sunucu kendi süresini söylediyse o geçerli."""
        sure = 15 * (deneme + 1)
        m = re.search(r"retry[^0-9]*([0-9]+)s", str(hata), re.IGNORECASE)
        if m:
            sure = int(m.group(1)) + 2
        self._bilgi(f"   ↻ Bağlantı hatası, {sure}s bekleniyor "
                    f"(deneme {deneme + 1}/{MAX_DENEME})...")
        # Saniye saniye uyunur: "Durdur"a basan kullanıcı 60 saniyenin
        # bitmesini beklemesin.
        for _ in range(sure):
            self._iptal_kontrol()
            self._uyu(1)

    def _siniflandir(self, hata: Exception) -> Exception:
        """Tükenmiş denemeyi kullanıcının anlayacağı bir hataya çevirir.

        Tanınmayan hata olduğu gibi döner: sessizce "atlandı"ya dönüşmesindense
        yukarı çıkıp görünmesi iyidir.
        """
        metin = (str(hata) + " " + type(hata).__name__).lower()
        if any(k in metin for k in ("timeout", "connection", "network", "ssl", "recv")):
            return InternetHatasi(
                "İnternet bağlantısı kurulamadı veya istek zaman aşımına uğradı. "
                "Bağlantınızı kontrol edip tekrar deneyin.")
        if "429" in metin or "rate" in metin or "quota" in metin:
            return InternetHatasi(
                "API istek limiti aşıldı. Birkaç dakika bekleyip tekrar başlatın.")
        return hata


def olustur(api_key: str, *, bilgi=None, iptal=None) -> ModelIstemcisi:
    """Gerçek Gemini istemcisini kurup dikişin ardına saklar."""
    client = genai.Client(api_key=api_key,
                          http_options={"timeout": TIMEOUT_SANIYE * 1000})
    return ModelIstemcisi(client, bilgi=bilgi, iptal=iptal)
