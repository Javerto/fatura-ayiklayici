"""
JS ↔ Python köprüsü.

Arayüz (web/) bu sınıfın metotlarını `pywebview.api.<metot>()` ile çağırır.
Arka plandaki worker ise `_log_q` kuyruğuna yazar; `_pompa` bu olayları
gruplayıp `window.olaylar([...])` ile arayüze iletir.

Eski `gui.py`'nin tkinter'dan bağımsız tüm sorumlulukları buraya taşındı.
"""

import base64
import json
import os
import pathlib
import queue
import sys
import threading
import time

import fitz
import webview
from dotenv import load_dotenv, set_key

from duzeltme import kural_ekle, kurallari_oku, kurallari_yaz
from excel_utils import ExcelHatasi, excel_olustur
from extraction import veri_dogrula
from review import (DUZENLENEBILIR_ALANLAR, form_satira_uygula, nihai_satirlar,
                    ogrenilecek_alanlar, satir_form_degerleri)
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

VARSAYILAN_BOYUT = (1040, 760)
EN_KUCUK_BOYUT   = (760, 560)

load_dotenv(dotenv_path=ENV_DOSYASI)


def pencere_boyutu() -> tuple[int, int]:
    """Kayıtlı pencere boyutu; kayıt yoksa veya bozuksa varsayılan.

    Yalnızca boyut saklanır, konum değil: uzak masaüstünde çözünürlük
    oturumlar arasında değişebiliyor ve kayıtlı bir konum pencereyi
    ekran dışında bırakabilir.
    """
    try:
        genislik, yukseklik = (int(p) for p in
                               os.environ.get("PENCERE", "").lower().split("x"))
    except ValueError:
        return VARSAYILAN_BOYUT
    if (EN_KUCUK_BOYUT[0] <= genislik <= 10000
            and EN_KUCUK_BOYUT[1] <= yukseklik <= 10000):
        return genislik, yukseklik
    return VARSAYILAN_BOYUT


class Api:
    def __init__(self):
        self._pencere = None
        self._log_q = queue.Queue()
        self._stop_event = threading.Event()
        self._klasor = ""
        self._cikti = ""
        self._atlanmis = []
        self._baslangic = 0.0
        self._review = None            # onay bekleyen worker çıktısı
        self._pdf_doc = None           # açık önizleme belgesi (yeniden kullanılır)
        self._pdf_yol = None

    # ── Arayüzden çağrılanlar ────────────────────────────────────────

    def baslangic_durumu(self) -> dict:
        """Açılışta arayüzün ihtiyaç duyduğu ayarlar."""
        tema = os.environ.get("TEMA", "mocha")
        # Klasör taşınmış/silinmiş olabilir; yoksa boş dönüp seçtiririz.
        son_klasor = os.environ.get("KLASOR", "")
        if son_klasor and os.path.isdir(son_klasor):
            self._klasor = son_klasor
        else:
            son_klasor = ""
        return {
            "tema": tema if tema in GECERLI_TEMALAR else "mocha",
            "api_key_var": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "kalite": os.environ.get("KALITE", "1.5"),
            "klasor": son_klasor,
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
        secim = self._pencere.create_file_dialog(webview.FileDialog.FOLDER)
        if not secim:
            return ""
        self._klasor = secim[0] if isinstance(secim, (list, tuple)) else secim
        self._ayar_yaz("KLASOR", self._klasor)
        return self._klasor

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
        self._klasor = klasor
        self._cikti = os.path.join(klasor, cikti_adi)
        self._atlanmis = []
        self._baslangic = time.time()
        self._stop_event.clear()
        self._log_q = queue.Queue()

        retry = ayarlar.get("retry") or None
        threading.Thread(
            target=worker,
            args=(api_key, klasor, cikti_adi, self._log_q, self._stop_event),
            kwargs={"zoom": float(ayarlar.get("kalite") or 1.5),
                    "kurallar": kurallari_oku(DUZELTME_DOSYASI),
                    "retry_dosyalar": retry},
            daemon=True,
        ).start()
        threading.Thread(target=self._pompa, daemon=True).start()
        return {"ok": True}

    def durdur(self) -> bool:
        self._stop_event.set()
        return True

    def yeniden_dene(self) -> dict:
        """Son çalışmada atlanan dosyaları tekrar dener."""
        if not self._atlanmis or not self._klasor:
            return {"hata": "Yeniden denenecek dosya yok."}
        yollar = [os.path.join(self._klasor, ad) for ad, _ in self._atlanmis]
        return self.basla({
            "klasor": self._klasor,
            "cikti": pathlib.Path(self._cikti).stem,
            "kalite": os.environ.get("KALITE", "1.5"),
            "retry": yollar,
        })

    def excel_ac(self) -> bool:
        if self._cikti and os.path.exists(self._cikti):
            os.startfile(self._cikti)
            return True
        return False

    # ── Gözden geçirme ekranı ────────────────────────────────────────

    def satir_dogrula(self, i: int, form: dict) -> list:
        """Formdaki hâliyle satırın uyarıları — düzenleme sırasında çağrılır."""
        if not self._review or i >= len(self._review["yeni"]):
            return []
        return veri_dogrula(form_satira_uygula(self._review["yeni"][i], form))

    def review_onayla(self, duzenlemeler: dict, haric: list,
                      hatirla: list) -> dict:
        """Düzenlemeleri uygular, kuralları öğrenir ve Excel'i yazar.

        duzenlemeler: {"<i>": {alan: metin}} — yalnızca dokunulan satırlar
        haric:        [i, ...]  Excel'e yazılmayacak satırlar
        hatirla:      [i, ...]  firma kuralı olarak kaydedilecek satırlar
        """
        if not self._review:
            return {"hata": "Gözden geçirilecek veri yok."}

        yeni = list(self._review["yeni"])
        for anahtar, form in (duzenlemeler or {}).items():
            i = int(anahtar)
            yeni[i] = form_satira_uygula(yeni[i], form)

        haric_kume = {int(x) for x in (haric or [])}
        nihai = nihai_satirlar(self._review["mevcut"], yeni, haric_kume)

        if len(nihai) == len(self._review["mevcut"]):
            # Tüm yeni faturalar hariç tutuldu — mevcut Excel'e dokunma.
            self._gecmis_kaydet(0, len(self._atlanmis))
            self._review = None
            return {"ok": True, "yazilan": 0, "dokunulmadi": True,
                    "cikti": self._mevcut_cikti()}

        try:
            excel_olustur(nihai, self._review["cikti"])
        except ExcelHatasi as e:
            return {"hata": str(e)}          # pencere açık kalsın, düzenlemeler kaybolmasın

        self._cikti = self._review["cikti"]
        kaydedilen = self._kurallari_ogren(yeni, hatirla, haric_kume)
        yazilan = len(nihai) - len(self._review["mevcut"])
        self._gecmis_kaydet(yazilan, len(self._atlanmis))
        self._review = None
        return {"ok": True, "yazilan": yazilan, "kural": kaydedilen,
                "cikti": self._cikti}

    def review_iptal(self) -> dict:
        self._review = None
        self._gecmis_kaydet(0, len(self._atlanmis))
        return {"ok": True, "cikti": self._mevcut_cikti()}

    def onizleme(self, i: int, sayfa: int, zoom: float) -> dict:
        """Faturanın PDF sayfasını PNG olarak döndürür (base64)."""
        if not self._review or i >= len(self._review["yeni"]):
            return {"hata": "Önizleme yok"}
        yol = str(self._review["yeni"][i].get("dosya_yolu") or "")
        if not yol.lower().endswith(".pdf") or not os.path.exists(yol):
            return {"hata": "Bu fatura için PDF yok"}
        try:
            if self._pdf_yol != yol:
                if self._pdf_doc is not None:
                    self._pdf_doc.close()
                self._pdf_doc = fitz.open(yol)
                self._pdf_yol = yol
            n = self._pdf_doc.page_count
            sayfa = max(0, min(int(sayfa), n - 1))
            zoom = max(0.5, min(3.0, float(zoom)))
            pix = self._pdf_doc[sayfa].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return {"png": base64.b64encode(pix.tobytes("png")).decode(),
                    "sayfa": sayfa, "toplam": n}
        except Exception as e:
            return {"hata": f"Önizleme yüklenemedi: {e}"}

    def dosya_ac(self, i: int) -> bool:
        """Faturanın kaynak dosyasını sistem uygulamasında açar."""
        if not self._review or i >= len(self._review["yeni"]):
            return False
        yol = str(self._review["yeni"][i].get("dosya_yolu") or "")
        if yol and os.path.exists(yol):
            os.startfile(yol)
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
            self._pencere.evaluate_js(kod)
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
                olaylar.append(self._log_q.get(timeout=0.2))
            except queue.Empty:
                continue
            while len(olaylar) < 60:
                try:
                    olaylar.append(self._log_q.get_nowait())
                except queue.Empty:
                    break

            gonderilecek = []
            for tag, veri in olaylar:
                if tag == "review":
                    # Satırlar Python'da kalır; arayüze yalnızca metin
                    # izdüşümü gider (datetime/float JSON'da tur atmasın).
                    self._review = veri
                    gonderilecek.append(self._review_olayi(veri))
                    bitti = True
                elif tag == "done":
                    atlanmis, islenen, _uyarilar = veri
                    self._atlanmis = atlanmis
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

    def _pencere_kapaniyor(self):
        """Kapanışta pencere boyutunu sakla (main.py'de closing'e bağlanır)."""
        try:
            self._ayar_yaz("PENCERE",
                           f"{int(self._pencere.width)}x{int(self._pencere.height)}")
        except Exception:
            pass          # boyut okunamazsa kapanışı engelleme

    def _mevcut_cikti(self) -> str:
        """Diskte gerçekten duran çıktı dosyasının yolu (yoksa boş)."""
        return self._cikti if self._cikti and os.path.exists(self._cikti) else ""

    def _review_olayi(self, payload: dict) -> dict:
        """Gözden geçirme ekranının ihtiyaç duyduğu metin izdüşümü."""
        self._atlanmis = payload["atlanmis"]
        satirlar = []
        for i, satir in enumerate(payload["yeni"]):
            yol = str(satir.get("dosya_yolu") or "")
            satirlar.append({
                "i":        i,
                "form":     satir_form_degerleri(satir),
                "uyarilar": veri_dogrula(satir),
                "dosya":    os.path.basename(yol),
                "pdf":      yol.lower().endswith(".pdf") and os.path.exists(yol),
                "kaynak":   satir.get("_teknik_bilgi")
                            or ("XML" if yol.lower().endswith(".xml") else ""),
            })
        return {"t": "review", "satirlar": satirlar,
                # Alan adı/etiketleri Python'dan gelir; arayüz yalnızca
                # gruplamayı bilir, yeni alan eklenirse kendiliğinden görünür.
                "alanlar": [list(a) for a in DUZENLENEBILIR_ALANLAR],
                "mevcut_sayi": len(payload["mevcut"]),
                "kesildi": payload.get("kesildi", False),
                "atlanan": len(payload["atlanmis"])}

    def _excel_yaz(self, payload: dict) -> dict:
        self._atlanmis = payload["atlanmis"]
        try:
            excel_olustur(payload["mevcut"] + payload["yeni"], payload["cikti"])
        except ExcelHatasi as e:
            self._gecmis_kaydet(0, len(payload["atlanmis"]))
            return {"t": "bitti", "hata": str(e), "yazilan": 0,
                    "atlanan": len(payload["atlanmis"]),
                    "cikti": self._mevcut_cikti()}
        self._cikti = payload["cikti"]
        yazilan = len(payload["yeni"])
        self._gecmis_kaydet(yazilan, len(payload["atlanmis"]))
        return {"t": "bitti", "yazilan": yazilan,
                "atlanan": len(payload["atlanmis"]), "cikti": payload["cikti"]}

    def _kurallari_ogren(self, satirlar: list, hatirla: list,
                         haric: set) -> int:
        """'Firma için hatırla' işaretli satırlardan VKN bazlı kural üretir."""
        kurallar = kurallari_oku(DUZELTME_DOSYASI)
        eklenen = 0
        for i in {int(x) for x in (hatirla or [])} - haric:
            if i >= len(satirlar):
                continue
            vkn = str(satirlar[i].get("vkn") or "").strip()
            alanlar = ogrenilecek_alanlar(satirlar[i])
            if vkn and alanlar:
                kurallar = kural_ekle(kurallar, vkn, alanlar)
                eklenen += 1
        if eklenen:
            try:
                kurallari_yaz(DUZELTME_DOSYASI, kurallar)
            except OSError:
                return 0
        return eklenen

    def _gecmis_kaydet(self, islenen: int, atlanan: int):
        kayit = {
            "tarih":   time.strftime("%Y-%m-%d %H:%M"),
            "klasor":  os.path.basename(self._klasor) or self._klasor,
            "dosya":   pathlib.Path(self._cikti).stem if self._cikti else "",
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
