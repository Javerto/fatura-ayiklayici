"""pdf_den_veri_cek — dışarıdan verilen metni kullanma (çift çıkarmayı önleme)."""

import extraction


class SahteIstemci:
    """gemini.ModelIstemcisi'nin yerine geçer: tek metot, sabit yanıt."""

    def __init__(self, json_text):
        self._yanit = json_text
        self.parcalar = None

    def metin_uret(self, parcalar):
        self.parcalar = parcalar
        return self._yanit


def test_verilen_metin_kullanilir_tekrar_cikarilmaz(monkeypatch):
    """metin parametresi verilince pdf_text_ayikla tekrar çağrılmamalı."""
    cagrilar = []
    monkeypatch.setattr(extraction, "pdf_text_ayikla",
                        lambda p: cagrilar.append(p) or "")

    istemci = SahteIstemci(
        '{"fatura_no": "GIB2024123456789", "fatura_tarihi": "2024-01-15", '
        '"vergiler_dahil_tutar": 100}')

    uzun_metin = "Fatura satir icerigi " * 20  # > 100 karakter → dijital
    veri = extraction.pdf_den_veri_cek("ornek.pdf", istemci, metin=uzun_metin)

    assert veri["fatura_no"] == "GIB2024123456789"
    assert veri["_teknik_bilgi"] == "Dijital"
    assert cagrilar == []  # metin dışarıdan geldi, tekrar çıkarılmadı


def test_metin_verilmezse_kendi_cikarir(monkeypatch):
    """metin verilmezse fonksiyon pdf_text_ayikla'yı bir kez çağırır."""
    cagrilar = []
    monkeypatch.setattr(extraction, "pdf_text_ayikla",
                        lambda p: cagrilar.append(p) or ("uzun metin " * 20))

    extraction.pdf_den_veri_cek(
        "ornek.pdf", SahteIstemci('{"fatura_no": "GIB2024123456789"}'))

    assert cagrilar == ["ornek.pdf"]  # tam olarak bir kez
