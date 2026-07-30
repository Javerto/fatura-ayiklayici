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

from api import Api

VERSION = "2.0"


def web_dosyasi(ad: str) -> str:
    """web/ altındaki bir dosyanın tam yolu (EXE modunda PyInstaller geçici klasörü)."""
    kok = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))
    return str(kok / "web" / ad)


def main():
    api = Api()
    # Pencere referansı `_` önekiyle saklanmalı: pywebview, arayüze açacağı
    # API nesnesinin genel niteliklerine özyineleyerek girer (webview/util.py
    # get_functions). Window nesnesi js_api'ye geri işaret ettiği için bu
    # halkada dönüp uygulamayı açılışta dondurur.
    api._pencere = webview.create_window(
        f"Fatura Ayıklama  v{VERSION}",
        web_dosyasi("index.html"),
        js_api=api,
        width=1040, height=760,
        min_size=(760, 560),
    )
    webview.start()


if __name__ == "__main__":
    main()
