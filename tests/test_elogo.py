import base64
import http.client
import json

import pytest

import elogo
from hatalar import ElogoHatasi, ElogoOturumHatasi


TOKEN = "sahte-token-123"
CUSTOMER = "sahte-musteri"


def yanit(veri, kod=200):
    return kod, json.dumps(veri).encode("utf-8")


class SahteGonder:
    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.aramalar = []

    def __call__(self, yontem, url, govde, basliklar):
        self.aramalar.append((yontem, url, govde, basliklar))
        return self.yanitlar.pop(0)


def istemci(gonder, simdi=1000):
    return elogo.ElogoIstemcisi(
        TOKEN, CUSTOMER, son_kullanma=simdi + 1000,
        gonder=gonder, saat=lambda: simdi)


def liste_ogesi(no, kimlik="id-1", **ek):
    return {"InvoiceId": kimlik, "InvoiceNumber": no, **ek}


def govde(arama):
    return json.loads(arama[2])


def test_101_numara_iki_parcaya_bolunur():
    gonder = SahteGonder([yanit({"Items": [], "TotalCount": 0}),
                          yanit({"Items": [], "TotalCount": 0})])
    istemci(gonder).fatura_bul([f"NO{i}" for i in range(101)])
    assert len(gonder.aramalar) == 2
    assert [len(govde(a)["invoiceNumbers"]) for a in gonder.aramalar] == [100, 1]
    assert all(govde(a)["pageSize"] == 100 for a in gonder.aramalar)


def test_sayfalama_offseti_ilerler_ve_eslesmeyenler_atilir():
    gonder = SahteGonder([
        yanit({"Items": [liste_ogesi("abc", "a"), liste_ogesi("baska", "b")],
               "TotalCount": 3}),
        yanit({"Items": [liste_ogesi("ABC", "c")], "TotalCount": 3}),
    ])
    sonuc = istemci(gonder).fatura_bul(["AbC"])
    assert [govde(a)["rowOffset"] for a in gonder.aramalar] == [0, 2]
    assert [x["InvoiceId"] for x in sonuc["AbC"]] == ["a", "c"]


def test_bos_sayfa_total_doluyken_hata_verir():
    gonder = SahteGonder([yanit({"Items": [], "TotalCount": 1})])
    with pytest.raises(ElogoHatasi):
        istemci(gonder).fatura_bul(["NO"])


def test_harf_duyarsiz_tekilleme_ve_coklu_eslesme():
    gonder = SahteGonder([yanit({"Items": [liste_ogesi("AbC", "1"),
                                             liste_ogesi("abc", "2")], "TotalCount": 2})])
    sonuc = istemci(gonder).fatura_bul(["ABC", "abc", "x"])
    assert list(sonuc) == ["ABC", "x"]
    assert [x["InvoiceId"] for x in sonuc["ABC"]] == ["1", "2"]
    assert sonuc["x"] == []


def test_bos_girdi_istek_atmaz():
    gonder = SahteGonder([])
    assert istemci(gonder).fatura_bul([]) == {}
    assert not gonder.aramalar


def test_liste_govdesi_tarih_icermez_musteri_doludur_ve_yetki_gonderilir():
    gonder = SahteGonder([yanit({"Items": [], "TotalCount": 0})])
    istemci(gonder).fatura_bul(["NO"])
    arama = gonder.aramalar[0]
    assert govde(arama)["customerIds"] == [CUSTOMER]
    assert "beginSystemCreated" not in govde(arama)
    assert "endSystemCreated" not in govde(arama)
    assert arama[3]["Authorization"] == f"Bearer {TOKEN}"
    assert arama[3]["Content-Type"] == "application/json"


def test_xml_indir_base64_cozer():
    xml = b"<Invoice>sahte</Invoice>"
    gonder = SahteGonder([yanit({"Payload": {"IsSuccess": True,
                                             "Document": base64.b64encode(xml).decode()}})])
    sonuc = istemci(gonder).xml_indir("id/özel")
    assert sonuc == xml
    assert "invoiceId=id%2F%C3%B6zel" in gonder.aramalar[0][1]
    assert gonder.aramalar[0][3] == {"Authorization": f"Bearer {TOKEN}"}


def test_suresi_dolmusken_istek_atilmaz():
    gonder = SahteGonder([])
    istemci_nesnesi = elogo.ElogoIstemcisi(
        TOKEN, CUSTOMER, son_kullanma=2000, gonder=gonder, saat=lambda: 2000)
    with pytest.raises(ElogoOturumHatasi):
        istemci_nesnesi.fatura_bul(["NO"])
    assert not gonder.aramalar


@pytest.mark.parametrize("simdi, expiry, sinif", [
    (1000, 1050, ElogoOturumHatasi),
    (1000, 2000, ElogoHatasi),
])
def test_http_hatalari_sureye_gore_siniflanir(simdi, expiry, sinif):
    gonder = SahteGonder([yanit({"Success": False}, 500)])
    istemci_nesnesi = elogo.ElogoIstemcisi(
        TOKEN, CUSTOMER, son_kullanma=expiry, gonder=gonder, saat=lambda: simdi)
    with pytest.raises(sinif):
        istemci_nesnesi.fatura_bul(["NO"])


@pytest.mark.parametrize("veri", [
    b"json degil",
    json.dumps([]).encode(),
    json.dumps({"Success": False}).encode(),
    json.dumps({"Items": [], "TotalCount": "1"}).encode(),
])
def test_liste_yanit_hatalari(veri):
    gonder = SahteGonder([(200, veri)])
    with pytest.raises(ElogoHatasi) as hata:
        istemci(gonder).fatura_bul(["NO"])
    assert b"json degil" not in str(hata.value).encode()


def test_oge_icerisinde_fatura_numarasi_eksikse_hata_verir():
    gonder = SahteGonder([yanit({"Items": [{"InvoiceId": "id"}], "TotalCount": 1})])
    with pytest.raises(ElogoHatasi):
        istemci(gonder).fatura_bul(["NO"])


@pytest.mark.parametrize("veri", [
    {"Success": True},
    {"Success": False},
    {"Success": True, "Payload": None},
    {"Success": True, "Payload": {"IsSuccess": False}},
    {"Success": True, "Payload": {"IsSuccess": True}},
    {"Success": True, "Payload": {"IsSuccess": True, "Document": "!bozuk!"}},
])
def test_xml_yanit_hatalari(veri):
    gonder = SahteGonder([yanit(veri)])
    with pytest.raises(ElogoHatasi):
        istemci(gonder).xml_indir("id")


def test_ag_hatasi_elogo_hatasi_ve_govdeyi_sizdirmaz():
    def patlayan(*args):
        raise OSError("gizli-govde")

    with pytest.raises(ElogoHatasi) as hata:
        istemci(patlayan).fatura_bul(["NO"])
    assert "gizli-govde" not in str(hata.value)


def test_http_exception_ag_hatasi_olur():
    def patlayan(*args):
        raise http.client.HTTPException("gizli-govde")

    with pytest.raises(ElogoHatasi):
        istemci(patlayan).fatura_bul(["NO"])


def test_token_repr_ve_hata_mesajinda_yoktur():
    gonder = SahteGonder([yanit({"Success": False}, 500)])
    istemci_nesnesi = istemci(gonder, simdi=1500)
    with pytest.raises(ElogoHatasi) as hata:
        istemci_nesnesi.fatura_bul(["NO"])
    assert TOKEN not in str(hata.value)
    assert TOKEN not in repr(istemci_nesnesi)

