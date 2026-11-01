"""Form değerini kaynak belgede bulma: biçim çeşitleri, tam eşleşme, koordinatlar."""
import fitz
import pytest

from api import Api
from extraction import pdf_deger_bul
from review import arama_metinleri


def _pdf(*sayfalar, dondur=0):
    doc = fitz.open()
    for satirlar in sayfalar:
        sayfa = doc.new_page()
        for n, satir in enumerate(satirlar):
            sayfa.insert_text((50, 60 + n * 25), satir)
        sayfa.set_rotation(dondur)
    return doc


@pytest.mark.parametrize("deger, tip, olmali", [
    ("1320.5", "sayi", "1.320,50"),
    ("1320.5", "sayi", "1,320.50"),
    ("1320.5", "sayi", "1320,50"),
    ("224000", "sayi", "224.000,00"),
    ("224000", "sayi", "224000"),
    ("1", "sayi", "1"),
    ("1", "sayi", "1,00"),
    ("30.11.2021", "tarih", "30-11-2021"),
    ("30.11.2021", "tarih", "2021-11-30"),
    ("30.11.2021", "tarih", "30/11/2021"),
    ("  KADIKÖY  ", "metin", "KADIKÖY"),
])
def test_arama_metinleri_belgedeki_bicimi_kapsar(deger, tip, olmali):
    assert olmali in arama_metinleri(deger, tip)[0]


def test_bos_deger_aranmaz():
    assert arama_metinleri("   ", "metin") == ([], False)
    assert arama_metinleri("", "sayi") == ([], False)


def test_cevrilemeyen_sayi_ve_tarih_yazildigi_gibi_aranir():
    # Kullanıcı formda yazarken ara değerler geçebilir; hata değil, sade arama.
    assert arama_metinleri("abc", "sayi")[0] == ["abc"]
    assert arama_metinleri("xx", "tarih")[0] == ["xx"]


def test_sayi_baska_sayinin_icinde_eslesmez():
    doc = _pdf(["Toplam: 1.100,00 TL", "Birim 100,00 TL"])
    metinler, tam = arama_metinleri("100", "sayi")
    bulunan = pdf_deger_bul(doc, metinler, tam)
    assert len(bulunan["kutular"]) == 1
    # İkinci satırdaki kutu: y, sayfanın üst kısmında ama ilk satırın altında.
    assert bulunan["kutular"][0][1] > 60 / doc[0].rect.height


def test_tek_haneli_miktar_tutarlarin_icinde_eslesmez():
    doc = _pdf(["1.100,00 TL", "Miktar 1 Adet", "KDV %18,00"])
    metinler, tam = arama_metinleri("1", "sayi")
    assert len(pdf_deger_bul(doc, metinler, tam)["kutular"]) == 1


def test_kisa_metin_kelime_icinde_eslesmez():
    doc = _pdf(["ATLAS MAKINE", "Para birimi: TL"])
    metinler, tam = arama_metinleri("TL", "metin")
    assert tam
    assert len(pdf_deger_bul(doc, metinler, tam)["kutular"]) == 1


def test_uzun_metin_parca_olarak_eslesir():
    doc = _pdf(["POLAR OTOMASYON MAKINE SAN."])
    metinler, tam = arama_metinleri("OTOMASYON MAKINE", "metin")
    assert not tam
    assert pdf_deger_bul(doc, metinler, tam)


def test_bulunamayan_none():
    assert pdf_deger_bul(_pdf(["Fatura"]), ["YOK123"], False) is None


def test_baska_sayfadaki_deger_bulunur_ve_sayfasi_doner():
    doc = _pdf(["Birinci"], ["Fatura No: ABC2026000000123"])
    assert pdf_deger_bul(doc, ["ABC2026000000123"], False)["sayfa"] == 1


def test_acik_sayfadaki_eslesme_once_gelir():
    doc = _pdf(["Tutar 500,00"], ["Tutar 500,00"])
    assert pdf_deger_bul(doc, ["500,00"], True, ilk_sayfa=1)["sayfa"] == 1
    assert pdf_deger_bul(doc, ["500,00"], True, ilk_sayfa=0)["sayfa"] == 0


def test_gecersiz_sayfa_numarasi_tasmaz():
    doc = _pdf(["Tutar 500,00"])
    assert pdf_deger_bul(doc, ["500,00"], True, ilk_sayfa=99)["sayfa"] == 0
    assert pdf_deger_bul(doc, ["500,00"], True, ilk_sayfa=-5)["sayfa"] == 0


@pytest.mark.parametrize("dondur", [0, 90, 180, 270])
def test_kutu_gorseldeki_yazinin_ustune_duser(dondur):
    """Kutu oransal gelir ve görselin üstüne çizilir: sayfa döndürülmüş olsa da
    işlenmiş görselde o bölgede gerçekten yazı (koyu piksel) olmalı."""
    doc = _pdf(["ABC2026000000123"], dondur=dondur)
    bulunan = pdf_deger_bul(doc, ["ABC2026000000123"], False)
    x, y, g, h = bulunan["kutular"][0]
    pix = doc[0].get_pixmap()
    assert 0 <= x < x + g <= 1 and 0 <= y < y + h <= 1
    koyu = 0
    for py in range(int(y * pix.height), int((y + h) * pix.height) + 1):
        for px in range(int(x * pix.width), int((x + g) * pix.width) + 1):
            if px < pix.width and py < pix.height and sum(pix.pixel(px, py)[:3]) < 300:
                koyu += 1
    assert koyu > 10


# ── Api ──────────────────────────────────────────────────────────────

def _api(tmp_path, yol, **satir):
    api = Api(kok=tmp_path)
    api._review = {"mevcut": [], "yeni": [{"dosya_yolu": str(yol), **satir}],
                   "atlanmis": [], "uyarilar": [], "cikti": str(tmp_path / "c.xlsx")}
    return api


def test_api_deger_bul_alan_tipine_gore_arar(tmp_path):
    yol = tmp_path / "a.pdf"
    _pdf(["Vergiler Dahil: 1.320,50 TL"]).save(yol)
    c = _api(tmp_path, yol).deger_bul(0, "vergiler_dahil_tutar", "1320.5", 0)
    assert c["sayfa"] == 0 and len(c["kutular"]) == 1


def test_api_deger_bul_bulamayinca_bos(tmp_path):
    yol = tmp_path / "a.pdf"
    _pdf(["Fatura"]).save(yol)
    assert _api(tmp_path, yol).deger_bul(0, "vkn", "1234567890", 0) == {}


@pytest.mark.parametrize("i, alan, metin, sayfa", [
    (99, "vkn", "1", 0),
    (-1, "vkn", "1", 0),
    ("x", "vkn", "1", 0),
    (0, ["liste"], "1", 0),
    (0, "vkn", None, 0),
    (0, "vkn", "1", "x"),
])
def test_api_deger_bul_js_guven_siniri(tmp_path, i, alan, metin, sayfa):
    yol = tmp_path / "a.pdf"
    _pdf(["Fatura"]).save(yol)
    assert _api(tmp_path, yol).deger_bul(i, alan, metin, sayfa) == {}


def test_api_deger_bul_dosya_yoksa_bos(tmp_path):
    assert _api(tmp_path, tmp_path / "yok.pdf").deger_bul(0, "vkn", "1", 0) == {}
