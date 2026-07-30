"""Api sınıfının pywebview sözleşmesine uyduğunu doğrular."""
from api import Api


def test_api_yalnizca_metot_yayinlar():
    """Genel niteliklerin hepsi çağrılabilir olmalı.

    pywebview (webview/util.py::get_functions) arayüze açacağı API nesnesinin
    genel niteliklerine tek tek özyineleyerek girer, `_` ile başlayanları
    atlar. Genel bir nesne niteliği bırakılırsa — özellikle pencerenin
    kendisi, ki js_api'ye geri işaret eder — tarama halkaya girip uygulamayı
    açılışta dondurur. Bu bir kez başımıza geldi; test onu geri getirmesin.
    """
    api = Api()
    for ad in dir(api):
        if ad.startswith("_"):
            continue
        assert callable(getattr(api, ad)), (
            f"Api.{ad} genel bir nitelik — iç durum '_' önekiyle saklanmalı")


def test_calisan_islem_varken_yeniden_baslatilmaz():
    """İkinci `basla` çağrısı `_log_q`'yu değiştirip ilk worker'ın tüm
    çıktısını okunmayan bir kuyrukta bırakıyordu — harcanan Gemini kotası
    boşa gidiyordu. Arayüz butonu kilitliyor ama JS bir güven sınırı."""
    api = Api()
    api._calisiyor = True
    assert api.basla({"klasor": ".", "cikti": "x"}) == {"hata": "Zaten bir işlem sürüyor."}
