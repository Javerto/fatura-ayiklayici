"""veri_dogrula tutar tutarlılık (örtük KDV oranı) testleri."""
from extraction import veri_dogrula


def _temiz_satir(**ek):
    """Tutar kontrolü dışındaki uyarıları tetiklemeyen taban satır."""
    s = {"fatura_no": "GIB2024123456789", "sirket_adi": "ACME",
         "vkn": "1234567890", "para_birimi": "TL"}
    s.update(ek)
    return s


def _tutar_uyarilari(satir):
    return [u for u in veri_dogrula(satir)
            if "Örtük KDV" in u or "KDV hariç tutardan" in u]


def test_yuzde20_kdv_uyari_yok():
    s = _temiz_satir(kdv_haric_tutar=100.0, vergiler_dahil_tutar=120.0)
    assert _tutar_uyarilari(s) == []


def test_dahil_haricten_kucuk_uyarir():
    s = _temiz_satir(kdv_haric_tutar=120.0, vergiler_dahil_tutar=100.0)
    uyarilar = _tutar_uyarilari(s)
    assert len(uyarilar) == 1
    assert "küçük" in uyarilar[0]


def test_sacma_oran_uyarir():
    s = _temiz_satir(kdv_haric_tutar=100.0, vergiler_dahil_tutar=137.0)
    uyarilar = _tutar_uyarilari(s)
    assert len(uyarilar) == 1
    assert "37" in uyarilar[0]          # %37.0 metinde geçmeli


def test_yuzde0_kdv_uyari_yok():
    s = _temiz_satir(kdv_haric_tutar=100.0, vergiler_dahil_tutar=100.0)
    assert _tutar_uyarilari(s) == []


def test_diger_gecerli_oranlar_uyari_yok():
    for oran in (1, 8, 10, 18, 20):
        s = _temiz_satir(kdv_haric_tutar=100.0,
                         vergiler_dahil_tutar=100.0 + oran)
        assert _tutar_uyarilari(s) == [], f"%{oran} yanlış alarm verdi"


def test_tolerans_kurus_yuvarlamasini_affeder():
    # 1234.56 * 1.20 = 1481.472 → 1481.47'ye yuvarlanmış (oran %19.9998…)
    s = _temiz_satir(kdv_haric_tutar=1234.56, vergiler_dahil_tutar=1481.47)
    assert _tutar_uyarilari(s) == []


def test_alan_bos_ise_kontrol_atlanir():
    assert _tutar_uyarilari(_temiz_satir(vergiler_dahil_tutar=120.0)) == []
    assert _tutar_uyarilari(_temiz_satir(kdv_haric_tutar=100.0)) == []
    assert _tutar_uyarilari(
        _temiz_satir(kdv_haric_tutar=0, vergiler_dahil_tutar=120.0)) == []
