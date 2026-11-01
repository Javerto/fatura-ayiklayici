"""
Fatura Ayıklama — Başlangıç noktası.

Kurulum:
    pip install -r requirements.txt

Kullanım:
    python main.py
"""

import pathlib
import sys

import webview

from api import Api, EN_KUCUK_BOYUT, pencere_boyutu

VERSION = "2.0"


def web_dosyasi(ad: str) -> str:
    """web/ altındaki bir dosyanın tam yolu (EXE modunda PyInstaller geçici klasörü)."""
    kok = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))
    return str(kok / "web" / ad)


def _webview2_uyarisi(hata: Exception):
    """WebView2 yoksa sessizce çökmek yerine ne yapılacağını anlat."""
    mesaj = (
        "Uygulama açılamadı.\n\n"
        "Bu program Microsoft Edge WebView2 bileşenini kullanıyor ve "
        "bilgisayarınızda kurulu görünmüyor.\n\n"
        "Kurmak için microsoft.com/edge/webview2 adresinden "
        '"Evergreen Standalone Installer" dosyasını indirip çalıştırın, '
        "ardından bu programı yeniden açın.\n\n"
        f"Teknik ayrıntı: {hata}"
    )
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, mesaj, "Fatura Ayıklama — WebView2 gerekli", 0x10)
    except Exception:
        print(mesaj)


def main():
    api = Api()
    # Pencere referansı `_` önekiyle saklanmalı: pywebview, arayüze açacağı
    # API nesnesinin genel niteliklerine özyineleyerek girer (webview/util.py
    # get_functions). Window nesnesi js_api'ye geri işaret ettiği için bu
    # halkada dönüp uygulamayı açılışta dondurur.
    genislik, yukseklik = pencere_boyutu()
    pencere = webview.create_window(
        f"Fatura Ayıklama  v{VERSION}",
        web_dosyasi("index.html"),
        js_api=api,
        width=genislik, height=yukseklik,
        min_size=EN_KUCUK_BOYUT,
    )
    api._pencere = pencere
    pencere.events.closing += api._pencere_kapaniyor
    try:
        webview.start()
    except Exception as e:          # en sık nedeni: WebView2 kurulu değil
        _webview2_uyarisi(e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
