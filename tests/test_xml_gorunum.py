"""XML'e gömülü XSLT şablonuyla fatura görüntüsü. Şablon faturayı kesenden gelir: güvenilmez."""
import base64
import pathlib

import pytest

from api import Api
from extraction import xml_gorunumu

XSL = 'xmlns:xsl="http://www.w3.org/1999/XSL/Transform"'
SABLON = f"""<xsl:stylesheet version="2.0" {XSL}
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <xsl:output method="html"/>
  <xsl:template match="/"><html><body><h1><xsl:value-of select="//cbc:ID"/></h1></body></html></xsl:template>
</xsl:stylesheet>"""


def _ek(icerik: str | bytes, ad="f.xslt") -> str:
    ham = icerik.encode() if isinstance(icerik, str) else icerik
    return f"""<cac:AdditionalDocumentReference><cbc:ID>1</cbc:ID><cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject filename="{ad}">{base64.b64encode(ham).decode()}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment></cac:AdditionalDocumentReference>"""


def _fatura(tmp_path, *ekler, doctype="", no="ABC2026000000123") -> str:
    yol = tmp_path / "f.xml"
    yol.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>{doctype}
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>{no}</cbc:ID>{"".join(ekler)}
</Invoice>""", "utf-8")
    return str(yol)


def test_gomulu_sablon_faturayi_gosterir(tmp_path):
    html = xml_gorunumu(_fatura(tmp_path, _ek(SABLON)))
    assert "<h1>ABC2026000000123</h1>" in html


def test_sablon_olmayan_ekler_atlanir(tmp_path):
    yol = _fatura(tmp_path, _ek(b"%PDF-1.4 ikili", "ek.pdf"), _ek("<belge/>", "ek.xml"), _ek(SABLON))
    assert "ABC2026000000123" in xml_gorunumu(yol)


@pytest.mark.parametrize("ekler", [
    (),
    (_ek(b"%PDF-1.4 ikili", "ek.pdf"),),
    (_ek("<xsl:stylesheet bozuk"),),
    ("""<cac:AdditionalDocumentReference><cac:Attachment>
        <cbc:EmbeddedDocumentBinaryObject>@@@@</cbc:EmbeddedDocumentBinaryObject>
        </cac:Attachment></cac:AdditionalDocumentReference>""",),
    ("""<cac:AdditionalDocumentReference><cac:Attachment>
        <cbc:EmbeddedDocumentBinaryObject/></cac:Attachment></cac:AdditionalDocumentReference>""",),
    (_ek(f"""<xsl:stylesheet version="1.0" {XSL}><xsl:template match="/">
        <xsl:message terminate="yes">dur</xsl:message></xsl:template></xsl:stylesheet>"""),),
])
def test_kullanilabilir_sablon_yoksa_none(tmp_path, ekler):
    assert xml_gorunumu(_fatura(tmp_path, *ekler)) is None


def test_ornek_fatura_sablonsuz():
    assert xml_gorunumu("tests/fixtures/ornek_fatura.xml") is None


def test_bozuk_veya_olmayan_dosya_none(tmp_path):
    bozuk = tmp_path / "b.xml"
    bozuk.write_text("<Invoice", "utf-8")
    assert xml_gorunumu(str(bozuk)) is None
    assert xml_gorunumu(str(tmp_path / "yok.xml")) is None


# ── Güvenlik: şablon yabancı koddur ──────────────────────────────────

def test_sablon_dosya_yazamaz(tmp_path):
    hedef = tmp_path / "yazildi.txt"
    sablon = f"""<xsl:stylesheet version="1.0" {XSL} xmlns:exsl="http://exslt.org/common"
        extension-element-prefixes="exsl"><xsl:template match="/">
        <exsl:document href="{hedef.as_uri()}"><a>x</a></exsl:document><html/></xsl:template></xsl:stylesheet>"""
    assert xml_gorunumu(_fatura(tmp_path, _ek(sablon))) is None
    assert not hedef.exists()


def test_sablon_yerel_dosya_okuyamaz(tmp_path):
    gizli = tmp_path / "gizli.xml"
    gizli.write_text("<g>GIZLI-DEGER</g>", "utf-8")
    sablon = f"""<xsl:stylesheet version="1.0" {XSL}><xsl:template match="/">
        <html><body><xsl:value-of select="document('{gizli.as_uri()}')"/></body></html>
        </xsl:template></xsl:stylesheet>"""
    assert "GIZLI-DEGER" not in (xml_gorunumu(_fatura(tmp_path, _ek(sablon))) or "")


@pytest.mark.parametrize("etiket", ["include", "import"])
def test_sablon_dis_dosya_baglayamaz(tmp_path, etiket):
    """xsl:include/import şablon derlenirken okunur; erişim denetimi yalnız
    dönüşüm sırasında geçerli olduğu için ayrıca reddedilmeli."""
    dis = tmp_path / "dis.xsl"
    dis.write_text(f"""<xsl:stylesheet version="1.0" {XSL}><xsl:template match="/">
        <html><body>DIS-SABLON</body></html></xsl:template></xsl:stylesheet>""", "utf-8")
    sablon = f"""<xsl:stylesheet version="1.0" {XSL}><xsl:{etiket} href="{dis.as_uri()}"/></xsl:stylesheet>"""
    assert xml_gorunumu(_fatura(tmp_path, _ek(sablon))) is None


def test_xml_varligi_yerel_dosya_sizdiramaz(tmp_path):
    gizli = tmp_path / "gizli.txt"
    gizli.write_text("GIZLI-DEGER", "utf-8")
    doctype = f'<!DOCTYPE Invoice [<!ENTITY x SYSTEM "{gizli.as_uri()}">]>'
    yol = _fatura(tmp_path, _ek(SABLON), doctype=doctype, no="&x;")
    assert "GIZLI-DEGER" not in (xml_gorunumu(yol) or "")


def test_sablondaki_varlik_yerel_dosya_sizdiramaz(tmp_path):
    gizli = tmp_path / "gizli.txt"
    gizli.write_text("GIZLI-DEGER", "utf-8")
    sablon = f"""<!DOCTYPE xsl:stylesheet [<!ENTITY x SYSTEM "{gizli.as_uri()}">]>
      <xsl:stylesheet version="1.0" {XSL}><xsl:template match="/">
      <html><body>&x;</body></html></xsl:template></xsl:stylesheet>"""
    assert "GIZLI-DEGER" not in (xml_gorunumu(_fatura(tmp_path, _ek(sablon))) or "")


# ── Api ──────────────────────────────────────────────────────────────

def _api(tmp_path, yol, **satir):
    api = Api(kok=tmp_path)
    api._review = {"mevcut": [], "yeni": [{"dosya_yolu": str(yol), **satir}],
                   "atlanmis": [], "uyarilar": [], "cikti": str(tmp_path / "c.xlsx")}
    return api


def test_api_onizleme_xml_html_dondurur(tmp_path):
    c = _api(tmp_path, _fatura(tmp_path, _ek(SABLON))).onizleme(0, 0, 1.0)
    assert "ABC2026000000123" in c["html"]


def test_api_onizleme_sablonsuz_xml_aciklar(tmp_path):
    assert "şablon" in _api(tmp_path, _fatura(tmp_path)).onizleme(0, 0, 1.0)["hata"]


def test_api_onizleme_olmayan_xml_hata(tmp_path):
    assert "hata" in _api(tmp_path, tmp_path / "yok.xml").onizleme(0, 0, 1.0)


def test_api_deger_bul_xml_de_arama_metni_dondurur(tmp_path):
    """XML'de arama görüntünün içinde, arayüzde yapılır; Python yalnız biçimleri verir."""
    c = _api(tmp_path, _fatura(tmp_path, _ek(SABLON))).deger_bul(0, "vergiler_dahil_tutar", "1320.5", 0)
    assert "1.320,50" in c["metinler"] and c["tam"] is True


def test_review_olayi_xml_i_bildirir(tmp_path):
    yol = pathlib.Path(_fatura(tmp_path, _ek(SABLON)))
    api = _api(tmp_path, yol)
    satir = api._review_olayi({"yeni": api._review["yeni"], "mevcut": [], "atlanmis": []})["satirlar"][0]
    assert satir["xml"] is True and satir["pdf"] is False
