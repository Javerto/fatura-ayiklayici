"""
Fatura Ayıklama — Başlangıç noktası.

Kurulum:
    pip install -r requirements.txt

Kullanım:
    python main.py
"""

import logging
import pathlib
import sys
import tempfile
import threading
from logging.handlers import RotatingFileHandler

import webview

from api import Api, EN_KUCUK_BOYUT, GUNLUK_DOSYASI, gunluk, pencere_boyutu

VERSION = "2.0"
WEB_DOSYALARI = ("app.js", "editor.js", "index.html", "review.js",
                 "style.css", "tema.css", "tema.js")


def SAGLIK_RAPORU() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / "FaturaAyiklayici-saglik.txt"


def web_dosyasi(ad: str) -> str:
    """web/ altındaki bir dosyanın tam yolu (EXE modunda PyInstaller geçici klasörü)."""
    kok = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))
    return str(kok / "web" / ad)


def saglik_kontrolu() -> int:
    """`--saglik`: paket eksiksiz mi? Pencere açmadan yanıtlar; 0 = sağlam.

    CI'daki EXE denemesi için. `--windowed` EXE çökünce hata penceresi açıp
    beklediğinden "süreç ayakta" kontrolü çökmüş EXE'yi de sağlam sayardı.
    """
    sorunlar = [f"eksik web dosyası: {ad}" for ad in WEB_DOSYALARI
                if not pathlib.Path(web_dosyasi(ad)).exists()]
    # Üstteki import'lar buraya gelmeden çalıştı. WinForms katmanı ise pencere
    # açılana kadar yüklenmiyor; pakette eksikse ancak kullanıcıda ortaya çıkar.
    try:
        import webview.platforms.winforms  # noqa: F401
    except Exception as e:
        sorunlar.append(f"WinForms yüklenemedi: {e!r}")
    # `--windowed` EXE'nin konsolu yok: neden CI çıktısına ancak dosyayla ulaşır.
    SAGLIK_RAPORU().write_text("\n".join(sorunlar) or "sağlam", "utf-8")
    return 1 if sorunlar else 0


def gunluk_kur(yol) -> None:
    """Hataları `yol`a yazdırır; dosya açılamazsa sessizce vazgeçer.

    `--windowed` EXE'nin konsolu yok: kullanıcıda olan hatanın izi başka hiçbir
    yerde kalmıyor. Dosya 512 KB'de döner, bir eskisi (`.1`) saklanır.

    Kök düzey WARNING'de kalır, yalnızca uygulamanın kaydedicisi INFO yazar:
    kütüphanelerin INFO satırları (httpx her isteğin adresini yazar) girmesin.
    Fatura içeriği günlüğe yazılmaz; dosya adı, klasör ve hata izi yazılır.
    """
    try:
        dosya = RotatingFileHandler(yol, maxBytes=512_000, backupCount=1,
                                    encoding="utf-8")
    except OSError:
        return          # salt okunur klasör: günlüksüz de açılsın
    dosya.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
    logging.getLogger().addHandler(dosya)
    gunluk.setLevel(logging.INFO)
    sys.excepthook = lambda tip, hata, iz: gunluk.critical(
        "Yakalanmamış hata", exc_info=(tip, hata, iz))
    threading.excepthook = lambda a: gunluk.critical(
        "Yakalanmamış thread hatası",
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


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
    if "--saglik" in sys.argv:
        raise SystemExit(saglik_kontrolu())
    gunluk_kur(GUNLUK_DOSYASI)
    gunluk.info("Açıldı: v%s%s", VERSION,
                " (EXE)" if getattr(sys, "frozen", False) else "")
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
        gunluk.exception("Pencere başlatılamadı")
        _webview2_uyarisi(e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
