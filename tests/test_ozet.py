"""ozet.ozet_hesapla saf mantık testleri."""
from datetime import datetime

from ozet import ozet_hesapla


def _satir(**kw):
    s = {"fatura_no": "X", "sirket_adi": "ACME", "para_birimi": "TL",
         "fatura_tarihi": datetime(2024, 3, 15), "vergiler_dahil_tutar": 120.0,
         "kdv_haric_tutar": 100.0, "_teknik_bilgi": "Dijital",
         "dosya_yolu": "a.pdf"}
    s.update(kw)
    return s


def test_bos_liste():
    o = ozet_hesapla([])
    assert o["genel"]["adet"] == 0
    assert o["genel"]["tutar"] == {}
    assert o["aylik"] == []
    assert o["sirket"] == []


def test_genel_toplamlar_para_birimi_bazinda():
    satirlar = [
        _satir(),
        _satir(para_birimi="EUR", vergiler_dahil_tutar=50.0,
               kdv_haric_tutar=40.0),
        _satir(vergiler_dahil_tutar=240.0, kdv_haric_tutar=200.0),
    ]
    o = ozet_hesapla(satirlar)
    assert o["genel"]["adet"] == 3
    assert o["genel"]["tutar"] == {"TL": 360.0, "EUR": 50.0}
    assert o["genel"]["kdv"] == {"TL": 60.0, "EUR": 10.0}


def test_para_birimi_bos_tl_sayilir():
    o = ozet_hesapla([_satir(para_birimi=None)])
    assert o["genel"]["tutar"] == {"TL": 120.0}


def test_kdv_alani_eksik_kdv_toplamina_girmez():
    o = ozet_hesapla([_satir(kdv_haric_tutar=None)])
    assert o["genel"]["adet"] == 1
    assert o["genel"]["tutar"] == {"TL": 120.0}
    assert o["genel"]["kdv"] == {}


def test_kaynak_dagilimi():
    satirlar = [_satir(), _satir(_teknik_bilgi="OCR"),
                _satir(_teknik_bilgi=None, dosya_yolu="b.xml"),
                _satir(_teknik_bilgi=None, dosya_yolu=None)]
    o = ozet_hesapla(satirlar)
    assert o["genel"]["kaynak"] == {"Dijital": 1, "OCR": 1, "XML": 1,
                                    "Bilinmiyor": 1}


def test_aylik_kronolojik_ve_bilinmiyor_sonda():
    satirlar = [
        _satir(fatura_tarihi=datetime(2024, 5, 1)),
        _satir(fatura_tarihi=datetime(2024, 3, 1)),
        _satir(fatura_tarihi="okunamadi"),
        _satir(fatura_tarihi=datetime(2024, 3, 20),
               vergiler_dahil_tutar=240.0, kdv_haric_tutar=200.0),
    ]
    o = ozet_hesapla(satirlar)
    aylar = [ay for ay, _ in o["aylik"]]
    assert aylar == ["2024-03", "2024-05", "Bilinmiyor"]
    mart = dict(o["aylik"])["2024-03"]
    assert mart["adet"] == 2
    assert mart["tutar"] == {"TL": 360.0}


def test_sirket_tutara_gore_azalan():
    satirlar = [
        _satir(sirket_adi="Kucuk", vergiler_dahil_tutar=10.0,
               kdv_haric_tutar=None),
        _satir(sirket_adi="Buyuk", vergiler_dahil_tutar=1000.0,
               kdv_haric_tutar=None),
        _satir(sirket_adi=None, vergiler_dahil_tutar=5.0,
               kdv_haric_tutar=None),
    ]
    o = ozet_hesapla(satirlar)
    adlar = [ad for ad, _ in o["sirket"]]
    assert adlar == ["Buyuk", "Kucuk", "Bilinmiyor"]
    assert dict(o["sirket"])["Buyuk"]["tutar"] == {"TL": 1000.0}


def test_tutar_sayisal_degilse_adette_sayilir_toplama_girmez():
    o = ozet_hesapla([_satir(vergiler_dahil_tutar=None,
                             kdv_haric_tutar=None)])
    assert o["genel"]["adet"] == 1
    assert o["genel"]["tutar"] == {}
