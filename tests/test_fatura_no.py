"""_duzelt_fatura_no — 17 karakterlik fatura numarasından fazla sıfırı temizleme."""

from extraction import _duzelt_fatura_no


def test_bastaki_fazla_sifir_silinir():
    """Sıra bölümü baştan fazla 0 ile gelirse o sıfır silinir, 16 karaktere iner."""
    # GIB2024 + 0123456789 (10 haneli, baştan fazla sıfır)
    sonuc, degisti = _duzelt_fatura_no("GIB20240123456789")
    assert sonuc == "GIB2024123456789"
    assert len(sonuc) == 16
    assert degisti is True


def test_ortadaki_sifir_korunur():
    """Sıra bölümünde baştan sıfır YOKSA, ortadaki meşru sıfır silinmemeli.

    Bu durumda hangi hanenin fazla olduğu belirsizdir; numarayı bozmak yerine
    olduğu gibi bırakıp (degisti=False) doğrulama uyarısına bırakırız.
    """
    # GIB2024 + 1234500678 (10 haneli ama baştan sıfır yok)
    sonuc, degisti = _duzelt_fatura_no("GIB20241234500678")
    assert sonuc == "GIB20241234500678"  # değişmeden döner
    assert degisti is False


def test_dogru_uzunluk_dokunulmaz():
    """16 karakterlik geçerli numara değiştirilmez."""
    sonuc, degisti = _duzelt_fatura_no("GIB2024123456789")
    assert sonuc == "GIB2024123456789"
    assert degisti is False


def test_bosluk_temizlenir():
    """Baştaki/sondaki boşluklar kırpılır."""
    sonuc, _ = _duzelt_fatura_no("  GIB2024123456789  ")
    assert sonuc == "GIB2024123456789"
