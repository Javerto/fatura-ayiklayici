"""excel_utils.py dosya yolu <-> file:// URL dönüşümleri."""

from excel_utils import dosya_url, url_dosya


def test_yerel_yol_url_donusumu():
    assert dosya_url("C:\\klasor\\fatura.pdf") == "file:///C:/klasor/fatura.pdf"


def test_yerel_url_yol_donusumu():
    assert url_dosya("file:///C:/klasor/fatura.pdf") == "C:\\klasor\\fatura.pdf"


def test_yerel_roundtrip():
    yol = "C:\\Faturalar\\2024\\ocak.pdf"
    assert url_dosya(dosya_url(yol)) == yol


def test_unc_yol_url_donusumu():
    assert dosya_url("\\\\sunucu\\paylasim\\fatura.pdf") == "file://sunucu/paylasim/fatura.pdf"


def test_unc_roundtrip():
    yol = "\\\\sunucu\\paylasim\\fatura.pdf"
    assert url_dosya(dosya_url(yol)) == yol


def test_eski_bozuk_unc_okunur():
    # Geriye dönük uyumluluk: eski hatalı format file://// ile başlar.
    # Mevcut davranış tek baştaki ters bölü üretir (legacy quirk).
    assert url_dosya("file:////sunucu/pay/f.pdf") == "\\sunucu\\pay\\f.pdf"
