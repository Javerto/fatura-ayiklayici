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
