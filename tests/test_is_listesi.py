"""İşlenecek dosya kuralı: arayüzdeki sayaç ile worker aynı listeyi görmeli."""
import os

from api import Api
from worker import is_listesi


def _klasor(tmp_path, *adlar):
    for ad in adlar:
        (tmp_path / ad).write_text("x", encoding="utf-8")
    return str(tmp_path)


def test_esi_olan_xml_ayri_fatura_sayilmaz(tmp_path):
    k = _klasor(tmp_path, "a.pdf", "a.xml", "b.xml", "c.pdf")
    pdf, xml = is_listesi(k)
    assert [os.path.basename(p) for p in pdf] == ["a.pdf", "c.pdf"]
    assert [os.path.basename(x) for x in xml] == ["b.xml"]


def test_uzanti_buyuk_harfli_olsa_da_eslesir(tmp_path):
    # Eski arayüz kuralı yalnızca ".pdf"/".PDF" deniyordu; ".Pdf" kaçıyordu.
    k = _klasor(tmp_path, "fatura.Pdf", "fatura.XML")
    pdf, xml = is_listesi(k)
    assert len(pdf) == 1 and xml == []


def test_diger_dosyalar_yok_sayilir(tmp_path):
    k = _klasor(tmp_path, "faturalar.xlsx", "not.txt")
    assert is_listesi(k) == ([], [])


def test_olmayan_klasor_bos_doner():
    assert is_listesi(r"C:\\boyle_bir_klasor_yok_42") == ([], [])


def test_arayuz_sayaci_ayni_kurali_kullanir(tmp_path):
    """klasor_ozeti ile worker'ın listesi ayrışırsa kullanıcıya yanlış sayı gider."""
    k = _klasor(tmp_path, "a.pdf", "a.xml", "b.xml", "c.Pdf")
    pdf, xml = is_listesi(k)
    ozet = Api(kok=tmp_path).klasor_ozeti(k)
    assert ozet == {"pdf": len(pdf), "xml": len(xml)} == {"pdf": 2, "xml": 1}
