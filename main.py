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

VERSION = "2.0"


def web_dosyasi(ad: str) -> str:
    """web/ altındaki bir dosyanın tam yolu (EXE modunda PyInstaller geçici klasörü)."""
    kok = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))
    return str(kok / "web" / ad)


def main():
    webview.create_window(
        f"Fatura Ayıklama  v{VERSION}",
        web_dosyasi("index.html"),
        width=1040, height=760,
        min_size=(760, 560),
    )
    webview.start()


if __name__ == "__main__":
    main()
