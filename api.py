"""
JS ↔ Python köprüsü.

Arayüz (web/) bu sınıfın metotlarını `pywebview.api.<metot>()` ile çağırır.
Arka plandaki worker ise `log_q` kuyruğuna yazar; `_pompa` bu olayları
gruplayıp `window.olaylar([...])` ile arayüze iletir.

Eski `gui.py`'nin tkinter'dan bağımsız tüm sorumlulukları buraya taşındı.
"""

import json
import os
import pathlib
import queue
import sys
import threading
import time

import webview
from dotenv import load_dotenv, set_key

from duzeltme import kurallari_oku
from excel_utils import ExcelHatasi, excel_olustur
from worker import worker

# EXE modunda ayarlar AppData'ya yazılır (kullanıcı görmez/silemez).
if getattr(sys, "frozen", False):
    _BASE = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / "FaturaAyiklayici"
    _BASE.mkdir(parents=True, exist_ok=True)
else:
    _BASE = pathlib.Path(__file__).parent

ENV_DOSYASI      = _BASE / ".env"
GECMIS_DOSYASI   = _BASE / "gecmis.json"
DUZELTME_DOSYASI = _BASE / "duzeltmeler.json"

GECERLI_TEMALAR = ("mocha", "macchiato", "frappe", "nord", "latte", "kagit")


class Api:
    def __init__(self):
        self.pencere = None
        self.log_q = queue.Queue()
        self.stop_event = threading.Event()
        self.klasor = ""
        self.cikti = ""
        self.atlanmis = []
        self._baslangic = 0.0
        load_dotenv(dotenv_path=ENV_DOSYASI)

    # ── Arayüzden çağrılanlar ────────────────────────────────────────

    def baslangic_durumu(self) -> dict:
        """Açılışta arayüzün ihtiyaç duyduğu ayarlar."""
        tema = os.environ.get("TEMA", "mocha")
        return {
            "tema": tema if tema in GECERLI_TEMALAR else "mocha",
            "api_key_var": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "kalite": os.environ.get("KALITE", "1.5"),
        }

    def tema_kaydet(self, ad: str) -> bool:
        if ad not in GECERLI_TEMALAR:
            return False
        return self._ayar_yaz("TEMA", ad)

    def kalite_kaydet(self, deger: str) -> bool:
        return self._ayar_yaz("KALITE", str(deger))

    def api_key_kaydet(self, key: str) -> bool:
        key = (key or "").strip()
        if not key:
            return False
        return self._ayar_yaz("GEMINI_API_KEY", key)

    def klasor_sec(self) -> str:
        """Klasör seçtirir ve içindeki fatura sayısını döndürür."""
        secim = self.pencere.create_file_dialog(webview.FOLDER_DIALOG)
        if not secim:
            return ""
        self.klasor = secim[0] if isinstance(secim, (list, tuple)) else secim
        return self.klasor

    def klasor_ozeti(self, klasor: str) -> dict:
        """Klasördeki PDF/XML sayısı — seçimden hemen sonra gösterilir."""
        try:
            adlar = os.listdir(klasor)
        except OSError:
            return {"pdf": 0, "xml": 0}
        pdf = [a for a in adlar if a.lower().endswith(".pdf")]
        # Eşi PDF olan XML'ler ayrı sayılmaz; worker da onları tek fatura sayar.
        xml = [a for a in adlar if a.lower().endswith(".xml")
               and a[:-4] + ".pdf" not in adlar and a[:-4] + ".PDF" not in adlar]
        return {"pdf": len(pdf), "xml": len(xml)}

    def basla(self, ayarlar: dict) -> dict:
        """İşlemi başlatır. Hata varsa {'hata': mesaj} döner."""
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return {"hata": "api_key"}
        klasor = (ayarlar.get("klasor") or "").strip()
        if not klasor or not os.path.isdir(klasor):
            return {"hata": "Lütfen geçerli bir klasör seçin."}

        cikti_adi = (ayarlar.get("cikti") or "faturalar").strip() + ".xlsx"
        self.klasor = klasor
        self.cikti = os.path.join(klasor, cikti_adi)
        self.atlanmis = []
        self._baslangic = time.time()
        self.stop_event.clear()
        self.log_q = queue.Queue()

        retry = ayarlar.get("retry") or None
        threading.Thread(
            target=worker,
            args=(api_key, klasor, cikti_adi, self.log_q, self.stop_event),
            kwargs={"zoom": float(ayarlar.get("kalite") or 1.5),
                    "kurallar": kurallari_oku(DUZELTME_DOSYASI),
                    "retry_dosyalar": retry},
            daemon=True,
        ).start()
        threading.Thread(target=self._pompa, daemon=True).start()
        return {"ok": True}

    def durdur(self) -> bool:
        self.stop_event.set()
        return True

    def yeniden_dene(self) -> dict:
        """Son çalışmada atlanan dosyaları tekrar dener."""
        if not self.atlanmis or not self.klasor:
            return {"hata": "Yeniden denenecek dosya yok."}
        yollar = [os.path.join(self.klasor, ad) for ad, _ in self.atlanmis]
        return self.basla({
            "klasor": self.klasor,
            "cikti": pathlib.Path(self.cikti).stem,
            "kalite": os.environ.get("KALITE", "1.5"),
            "retry": yollar,
        })

    def excel_ac(self) -> bool:
        if self.cikti and os.path.exists(self.cikti):
            os.startfile(self.cikti)
            return True
        return False

    def gecmis(self) -> list:
        try:
            kayitlar = json.loads(GECMIS_DOSYASI.read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return list(reversed(kayitlar[-20:]))

    # ── İç yardımcılar ───────────────────────────────────────────────

    def _ayar_yaz(self, anahtar: str, deger: str) -> bool:
        try:
            set_key(str(ENV_DOSYASI), anahtar, deger)
        except OSError:
            return False
        os.environ[anahtar] = deger
        return True

    def _js(self, fonksiyon: str, *argumanlar):
        kod = "window.%s(%s)" % (
            fonksiyon,
            ",".join(json.dumps(a, ensure_ascii=False, default=str) for a in argumanlar))
        try:
            self.pencere.evaluate_js(kod)
        except Exception:
            pass   # pencere kapanmışsa olayı sessizce düşür

    def _pompa(self):
        """Kuyruğu boşaltıp olayları gruplar hâlinde arayüze yollar.

        Gruplama şart: 5 paralel PDF saniyede onlarca olay üretebiliyor,
        her biri için ayrı evaluate_js çağrısı arayüzü kilitler.
        """
        bitti = False
        while not bitti:
            olaylar = []
            try:
                olaylar.append(self.log_q.get(timeout=0.2))
            except queue.Empty:
                continue
            while len(olaylar) < 60:
                try:
                    olaylar.append(self.log_q.get_nowait())
                except queue.Empty:
                    break

            gonderilecek = []
            for tag, veri in olaylar:
                if tag == "review":
                    gonderilecek.append(self._excel_yaz(veri))
                    bitti = True
                elif tag == "done":
                    atlanmis, islenen, _uyarilar = veri
                    self.atlanmis = atlanmis
                    self._gecmis_kaydet(islenen, len(atlanmis))
                    # Yeni fatura çıkmamış olabilir ama Excel önceki
                    # çalışmalardan duruyorsa kullanıcı yine de açabilmeli.
                    gonderilecek.append({"t": "bitti", "yazilan": 0,
                                         "atlanan": len(atlanmis),
                                         "cikti": self._mevcut_cikti()})
                    bitti = True
                else:
                    gonderilecek.append({"t": tag, "d": veri})

            if gonderilecek:
                self._js("olaylar", gonderilecek)

    def _mevcut_cikti(self) -> str:
        """Diskte gerçekten duran çıktı dosyasının yolu (yoksa boş)."""
        return self.cikti if self.cikti and os.path.exists(self.cikti) else ""

    def _excel_yaz(self, payload: dict) -> dict:
        # ponytail: geçici — 4. aşamada gözden geçirme ekranı araya girecek.
        # Şu an çıkarılan her satır doğrudan Excel'e yazılıyor.
        self.atlanmis = payload["atlanmis"]
        try:
            excel_olustur(payload["mevcut"] + payload["yeni"], payload["cikti"])
        except ExcelHatasi as e:
            self._gecmis_kaydet(0, len(payload["atlanmis"]))
            return {"t": "bitti", "hata": str(e), "yazilan": 0,
                    "atlanan": len(payload["atlanmis"]),
                    "cikti": self._mevcut_cikti()}
        self.cikti = payload["cikti"]
        yazilan = len(payload["yeni"])
        self._gecmis_kaydet(yazilan, len(payload["atlanmis"]))
        return {"t": "bitti", "yazilan": yazilan,
                "atlanan": len(payload["atlanmis"]), "cikti": payload["cikti"]}

    def _gecmis_kaydet(self, islenen: int, atlanan: int):
        kayit = {
            "tarih":   time.strftime("%Y-%m-%d %H:%M"),
            "klasor":  os.path.basename(self.klasor) or self.klasor,
            "dosya":   pathlib.Path(self.cikti).stem if self.cikti else "",
            "islenen": islenen,
            "atlanan": atlanan,
            "sure_dk": round((time.time() - self._baslangic) / 60, 1),
        }
        try:
            gecmis = json.loads(GECMIS_DOSYASI.read_text("utf-8")) \
                     if GECMIS_DOSYASI.exists() else []
        except ValueError:
            gecmis = []
        gecmis.append(kayit)
        try:
            GECMIS_DOSYASI.write_text(
                json.dumps(gecmis[-100:], ensure_ascii=False, indent=2), "utf-8")
        except OSError:
            pass
