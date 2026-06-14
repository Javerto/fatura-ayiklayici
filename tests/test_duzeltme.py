"""duzeltme.py — öğrenen düzeltme kuralları saf mantık testleri."""
from duzeltme import (OGRENILEN_ALANLAR, kurallari_oku, kurallari_yaz,
                      kural_uygula, kural_ekle)


def test_ogrenilen_alanlar_para_birimi_iceremez():
    assert set(OGRENILEN_ALANLAR) == {"sirket_adi", "vergi_dairesi"}


def test_kurallari_oku_dosya_yoksa_bos_doner(tmp_path):
    assert kurallari_oku(tmp_path / "yok.json") == {}


def test_kurallari_oku_bozuk_json_bos_doner(tmp_path):
    yol = tmp_path / "bozuk.json"
    yol.write_text("{ bu gecersiz", encoding="utf-8")
    assert kurallari_oku(yol) == {}


def test_kurallari_yaz_ve_oku_roundtrip(tmp_path):
    yol = tmp_path / "k.json"
    veri = {"1234567890": {"sirket_adi": "ACME A.Ş."}}
    kurallari_yaz(yol, veri)
    assert kurallari_oku(yol) == veri


def test_kural_uygula_eslesirse_alanlari_ezer():
    kurallar = {"1234567890": {"sirket_adi": "ARÇELİK A.Ş.",
                               "vergi_dairesi": "Büyük Mükellefler"}}
    satir = {"vkn": "1234567890", "sirket_adi": "ARCELIK AS",
             "vergi_dairesi": "", "fatura_no": "X"}
    sonuc = kural_uygula(satir, kurallar)
    assert sonuc["sirket_adi"] == "ARÇELİK A.Ş."
    assert sonuc["vergi_dairesi"] == "Büyük Mükellefler"
    assert sonuc["fatura_no"] == "X"        # öğrenilmeyen alan korunur


def test_kural_uygula_eslesmezse_degismez():
    kurallar = {"1111111111": {"sirket_adi": "X"}}
    satir = {"vkn": "9999999999", "sirket_adi": "ORİJİNAL"}
    assert kural_uygula(satir, kurallar)["sirket_adi"] == "ORİJİNAL"


def test_kural_uygula_vkn_yoksa_degismez():
    kurallar = {"1234567890": {"sirket_adi": "X"}}
    satir = {"sirket_adi": "ORİJİNAL"}
    assert kural_uygula(satir, kurallar)["sirket_adi"] == "ORİJİNAL"


def test_kural_uygula_orijinali_bozmaz():
    kurallar = {"1234567890": {"sirket_adi": "YENİ"}}
    satir = {"vkn": "1234567890", "sirket_adi": "ESKİ"}
    kural_uygula(satir, kurallar)
    assert satir["sirket_adi"] == "ESKİ"     # kopya döner, mutasyon yok


def test_kural_ekle_yeni_vkn_ekler():
    sonuc = kural_ekle({}, "1234567890",
                       {"sirket_adi": "ACME", "vergi_dairesi": "Kadıköy"})
    assert sonuc == {"1234567890": {"sirket_adi": "ACME",
                                    "vergi_dairesi": "Kadıköy"}}


def test_kural_ekle_bos_degerleri_atlar():
    sonuc = kural_ekle({}, "1234567890",
                       {"sirket_adi": "ACME", "vergi_dairesi": "   "})
    assert sonuc == {"1234567890": {"sirket_adi": "ACME"}}


def test_kural_ekle_tum_degerler_bossa_kural_olusmaz():
    assert kural_ekle({}, "1234567890",
                      {"sirket_adi": "", "vergi_dairesi": None}) == {}


def test_kural_ekle_vkn_bossa_degismez():
    assert kural_ekle({"a": {"sirket_adi": "X"}}, "", {"sirket_adi": "Y"}) == \
        {"a": {"sirket_adi": "X"}}


def test_kural_ekle_orijinali_bozmaz():
    kurallar = {"1234567890": {"sirket_adi": "ESKİ"}}
    kural_ekle(kurallar, "1234567890", {"sirket_adi": "YENİ"})
    assert kurallar["1234567890"]["sirket_adi"] == "ESKİ"
