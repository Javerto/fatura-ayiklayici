"""Api sınıfının pywebview sözleşmesine uyduğunu doğrular."""
import threading

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


def test_es_zamanli_iki_basla_cagrisindan_biri_reddedilir(tmp_path, monkeypatch):
    """`_calisiyor` bayrağı worker thread'i başlatıldıktan *sonra* set
    edildiğinde iki eşzamanlı çağrı da guard'ı geçebiliyordu; pywebview her
    js_api çağrısını ayrı thread'de işliyor. İki worker demek, ilkinin
    çıktısının (ve harcadığı Gemini kotasının) çöpe gitmesi demek.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    api = Api(kok=tmp_path)
    monkeypatch.setattr("api.worker", lambda *a, **k: None)
    monkeypatch.setattr(api, "_pompa", lambda: None)

    kapi = threading.Barrier(2)
    sonuclar = []

    def cagir():
        kapi.wait()
        sonuclar.append(api.basla({"klasor": str(tmp_path), "cikti": "x"}))

    threadler = [threading.Thread(target=cagir) for _ in range(2)]
    for t in threadler:
        t.start()
    for t in threadler:
        t.join()

    assert sum("ok" in s for s in sonuclar) == 1, sonuclar
