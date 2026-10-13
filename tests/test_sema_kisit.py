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
