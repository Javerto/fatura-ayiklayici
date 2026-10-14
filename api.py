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

import fatura
import gemini
import sema
from duzeltme import kural_ekle, kurallari_oku, kurallari_yaz
from excel_utils import excel_olustur
from extraction import pdf_den_veri_cek, veri_dogrula
from hatalar import (APIKeyHatasi, ExcelHatasi, InternetHatasi, ModelHatasi,
                     PDFHatasi)
from review import (form_satira_uygula, nihai_satirlar,
                    ogrenilecek_alanlar, satir_form_degerleri)
from worker import is_listesi, worker

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
    def __init__(self, kok: pathlib.Path | None = None):
        # Ayar dosyaları örnek başına: modül sabiti olduklarında `review_onayla`
        # gibi yazan yolları test etmek geliştiricinin gerçek .env / gecmis.json
        # / duzeltmeler.json dosyalarını kirletiyordu.
        kok = pathlib.Path(kok) if kok else _BASE
        self._env      = kok / ".env"
        self._gecmis   = kok / "gecmis.json"
        self._duzeltme = kok / "duzeltmeler.json"
        self._alanlar  = kok / "alanlar.json"
        # İlk açılışta dosya tohumdan yazılır. Koşu başlarken yeniden okunur;
        # gözden geçirme ve onay o koşunun şemasıyla çalışır.
        self._sema = sema.oku(self._alanlar)
        self._pencere = None
        self._log_q = queue.Queue()
        self._stop_event = threading.Event()
        self._klasor = ""
        self._cikti = ""
        self._atlanmis = []
        self._baslangic = 0.0
        self._review = None            # onay bekleyen worker çıktısı
        self._calisiyor = False        # bir worker sürüyor mu
        self._deneniyor = False        # editörde bir "Dene" sürüyor mu
        self._baslatma_kilidi = threading.Lock()   # `basla` kontrol-ve-ata
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
        # Kural worker ile ortak: eşi PDF olan XML ayrı fatura sayılmaz.
        # (Mevcut Excel'de işlenmiş olanlar burada düşülmez — bu sayı klasörün
        # içeriğidir, işlenecek fatura sayısı değil.)
        pdf, xml = is_listesi(klasor)
        return {"pdf": len(pdf), "xml": len(xml)}

    def basla(self, ayarlar: dict) -> dict:
        """İşlemi başlatır. Hata varsa {'hata': mesaj} döner."""
        # Arayüz butonu kilitliyor ama JS bir güven sınırı: ikinci bir çağrı
        # `_log_q`'yu değiştirip ilk worker'ın tüm çıktısını (harcanan kotayla
        # birlikte) okunmayan bir kuyrukta bırakıyordu.
        # Kilit şart: pywebview her js_api çağrısını ayrı thread'de işliyor,
        # bayrağı thread başlatıldıktan sonra set etmek iki çağrının da
        # guard'ı geçmesine izin veriyordu.
        with self._baslatma_kilidi:
            if self._calisiyor or self._deneniyor:
                return {"hata": "Zaten bir işlem sürüyor."}
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                return {"hata": "api_key"}
            klasor = (ayarlar.get("klasor") or "").strip()
            if not klasor or not os.path.isdir(klasor):
                return {"hata": "Lütfen geçerli bir klasör seçin."}
            # Bozuk şemayla koşmak = tohumla koşmak: kullanıcının kendi
            # alanları okunmaz ve onayla arşivden düşer. Sessizce devam etme.
            s, sema_hatasi = sema.oku_ayrintili(self._alanlar)
            if sema_hatasi:
                return {"hata": f"Alan tanımları okunamadı ({sema_hatasi}). "
                                "Alanlar ekranından alanları kontrol edip kaydedin.",
                        "sema_hatasi": True}

            cikti_adi = (ayarlar.get("cikti") or "faturalar").strip() + ".xlsx"
            self._klasor = klasor
            self._cikti = os.path.join(klasor, cikti_adi)
            self._atlanmis = []
            self._baslangic = time.time()
            self._stop_event.clear()
            self._log_q = queue.Queue()
            self._calisiyor = True
            self._sema = s

            retry = ayarlar.get("retry") or None
            threading.Thread(
                target=worker,
                args=(api_key, klasor, cikti_adi, self._log_q, self._stop_event),
                kwargs={"zoom": float(ayarlar.get("kalite") or 1.5),
                        "kurallar": kurallari_oku(self._duzeltme),
                        "retry_dosyalar": retry,
                        "sema": self._sema},
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

    # ── Şema editörü ─────────────────────────────────────────────────

    def sema_oku(self) -> dict:
        """Editörün açılış verisi: dosyadaki şema, sütun numaraları hariç.

        `anahtar` yalnızca kimlik olarak gider (kaydederken alanı eşlemek
        için); arayüz onu göstermez.
        """
        if self._calisiyor:
            return {"hata": "Bir işlem sürerken alanlar düzenlenemez."}
        s, hata = sema.oku_ayrintili(self._alanlar)
        return {"alanlar": [
                    {**{k: a[k] for k in ("anahtar", "etiket", "tip", "aciklama",
                                          "cekirdek", "aktif", "zorunlu", "ogrenilir")},
                     "ogrenilebilir": sema.ogrenilebilir(a["anahtar"], a["tip"])}
                    for a in s.json()["alanlar"]],
                "tipler": list(sema.TIPLER),
                "sistem_basliklar": [a.baslik for a in sema.SISTEM_ALANLARI if a.baslik],
                "dosya_hatasi": hata}

    def sema_kaydet(self, alanlar: list) -> dict:
        """Editördeki alan listesini (sırasıyla) `alanlar.json`'a yazar.

        Çalışan koşunun şeması (`self._sema`) değişmez; yeni şema bir sonraki
        `basla()`'da okunur. Kayıt kilidi `basla` ile ortak: kontrol ile yazma
        arasında bir koşu başlamasın.
        """
        with self._baslatma_kilidi:
            if self._calisiyor or self._deneniyor:
                return {"hata": "Bir işlem ya da deneme sürerken alanlar kaydedilemez."}
            try:
                s = sema.coz({"surum": sema.SURUM,
                              "alanlar": self._editor_alanlari(alanlar)})
                sema.yaz(self._alanlar, s)
            except (ValueError, OSError) as e:
                return {"hata": f"Kaydedilemedi: {e}"}
        return {"ok": True}

    def dene_sec(self) -> str:
        """Denenecek PDF'i seçtirir (son klasörden başlar); vazgeçilirse boş."""
        secim = self._pencere.create_file_dialog(
            webview.FileDialog.OPEN, directory=self._klasor or "",
            file_types=("PDF faturalar (*.pdf)",))
        if not secim:
            return ""
        return secim[0] if isinstance(secim, (list, tuple)) else secim

    def dene(self, yol: str) -> dict:
        """Tek bir PDF'i KAYITLI şemayla modele gönderip çıkan alanları döndürür.

        Excel'e ve geçmişe hiçbir şey yazılmaz. Worker kullanılmıyor: o eşi
        olan XML'i modelsiz okur (açıklama denenmemiş olur) ve arşivi okur
        (bozuk bir Excel denemeyi engellerdi). Öğrenilen firma kuralları da
        uygulanmaz — kullanıcı açıklamasının modelden ne çıkardığını görmeli.
        """
        # JS bir güven sınırı: yol arayüzden gelir.
        if not (isinstance(yol, str) and yol.lower().endswith(".pdf")
                and os.path.isfile(yol)):
            return {"hata": "Denemek için bir PDF fatura seçin."}
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return {"hata": "api_key"}
        # Kilit `basla` ile ortak: deneme ile koşu aynı kotayı harcar ve aynı
        # `_stop_event`'i paylaşır (Durdur ve pencere kapanışı ikisini de keser).
        with self._baslatma_kilidi:
            if self._calisiyor or self._deneniyor:
                return {"hata": "Zaten bir işlem ya da deneme sürüyor."}
            self._deneniyor = True
            self._stop_event.clear()
        try:
            return self._dene(yol, api_key)
        finally:
            self._deneniyor = False

    def _dene(self, yol: str, api_key: str) -> dict:
        s = sema.oku(self._alanlar)
        try:
            # `olustur` süreç ömürlü sınırlayıcıyı kullanır: kota anahtara ait.
            istemci = gemini.olustur(api_key, iptal=self._stop_event)
            satir = pdf_den_veri_cek(yol, istemci,
                                     float(os.environ.get("KALITE", "1.5")), sema=s)
        except (APIKeyHatasi, PDFHatasi) as e:
            return {"hata": str(e)}
        except InternetHatasi as e:
            return {"hata": "Deneme durduruldu." if self._stop_event.is_set()
                    else str(e)}
        except ModelHatasi:
            return {"hata": "Model okunabilir bir yanıt vermedi. Tekrar deneyin; "
                            "sürerse alan açıklamalarını sadeleştirin."}
        except Exception as e:
            return {"hata": f"Beklenmedik hata — {type(e).__name__}: {e}"}
        degerler = satir_form_degerleri(satir, s)
        return {"dosya": fatura.dosya_adi(satir),
                "kaynak": fatura.kaynak(satir),
                "alanlar": [[a, e, degerler[a]] for a, e, _ in s.duzenlenebilir],
                "uyarilar": veri_dogrula(satir, sema=s)}

    def _editor_alanlari(self, alanlar) -> list[dict]:
        """Editörden gelen listeyi mevcut dosyayla birleştirip ham şemaya çevirir.

        JS bir güven sınırı: sütun, çekirdek ve genişlik hiçbir zaman arayüzden
        alınmaz; mevcut alanın tipi değiştirilemez (aynı Excel sütununda metin
        ve sayı karışır); mevcut bir alan listeden düşemez (silmek = pasife
        almak — düşen alanın sütunu yeni bir alana verilebilirdi).
        """
        if not isinstance(alanlar, list):
            raise ValueError("alan listesi bekleniyordu")
        mevcut = {a["anahtar"]: a for a in
                  sema.oku(self._alanlar).json()["alanlar"]}
        ham, gorulen = [], set()
        for d in alanlar:
            if not isinstance(d, dict):
                raise ValueError("geçersiz alan")
            anahtar = d.get("anahtar")
            if anahtar:
                if anahtar not in mevcut or anahtar in gorulen:
                    raise ValueError("bilinmeyen ya da yinelenen alan")
                gorulen.add(anahtar)
                a = dict(mevcut[anahtar])
                if d.get("tip", a["tip"]) != a["tip"]:
                    raise ValueError(f"“{a['etiket']}” alanının tipi değiştirilemez")
            else:                       # yeni alan: anahtar ve sütunu coz atar
                a = {"tip": d.get("tip")}
            a.update(etiket=d.get("etiket"), aciklama=str(d.get("aciklama") or ""),
                     aktif=bool(d.get("aktif", True)),
                     zorunlu=bool(d.get("zorunlu", False)),
                     ogrenilir=bool(d.get("ogrenilir", False)))
            ham.append(a)
        eksik = set(mevcut) - gorulen
        if eksik:
            raise ValueError("listeden alan eksik (kaldırmak için pasife alın)")
        return ham

    # ── Gözden geçirme ekranı ────────────────────────────────────────

    def _satir(self, i):
        """Gözden geçirme satırı; geçersiz indekste None.

        JS bir güven sınırı: `i >= len` kontrolü negatif indeksi geçiriyordu
        (i = -1 sessizce son satırı döndürür) ve sayı olmayan değerde
        TypeError atıyordu.
        """
        if not self._review:
            return None
        try:
            i = int(i)
        except (TypeError, ValueError):
            return None
        yeni = self._review["yeni"]
        return yeni[i] if 0 <= i < len(yeni) else None

    def _baska_nolar(self, haric_i: int | None = None) -> set[str]:
        """Fatura no'ları — mükerrer uyarısı için karşılaştırma kümesi.

        Arşivdeki her no, artı yeni satırlarda birden fazla geçen no'lar.
        `haric_i` verilirse o satır yokmuş gibi hesaplanır (düzenlenen satır).
        """
        r = self._review or {"mevcut": [], "yeni": []}
        nolar = {fatura.fatura_no_anahtari(s) for s in r["mevcut"]}
        yeni = [fatura.fatura_no_anahtari(s) for j, s in enumerate(r["yeni"])
                if j != haric_i]
        if haric_i is None:
            # Tek satır için değil, tüm liste için: iki kez geçen no mükerrerdir.
            nolar |= {n for n in yeni if yeni.count(n) > 1}
        else:
            nolar |= set(yeni)
        nolar.discard("")
        return nolar

    def satir_dogrula(self, i: int, form: dict) -> list:
        """Formdaki hâliyle satırın uyarıları — düzenleme sırasında çağrılır."""
        satir = self._satir(i)
        if not satir:
            return []
        return veri_dogrula(form_satira_uygula(satir, form, self._sema),
                            self._baska_nolar(haric_i=int(i)), self._sema)

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
            try:
                i = int(anahtar)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(yeni):
                yeni[i] = form_satira_uygula(yeni[i], form, self._sema)

        haric_kume = {int(x) for x in (haric or [])}
        nihai = nihai_satirlar(self._review["mevcut"], yeni, haric_kume)

        if len(nihai) == len(self._review["mevcut"]):
            # Tüm yeni faturalar hariç tutuldu — mevcut Excel'e dokunma.
            self._gecmis_kaydet(0, len(self._atlanmis))
            self._onizlemeyi_kapat()
            self._review = None
            return {"ok": True, "yazilan": 0, "dokunulmadi": True,
                    "cikti": self._mevcut_cikti()}

        try:
            # Worker'ın arşiv şeması: arşive özgü sütunlar da yazılsın.
            excel_olustur(nihai, self._review["cikti"],
                          self._review.get("sema") or self._sema)
        except ExcelHatasi as e:
            return {"hata": str(e)}          # pencere açık kalsın, düzenlemeler kaybolmasın

        self._cikti = self._review["cikti"]
        self._onizlemeyi_kapat()
        kaydedilen = self._kurallari_ogren(yeni, hatirla, haric_kume)
        yazilan = len(nihai) - len(self._review["mevcut"])
        self._gecmis_kaydet(yazilan, len(self._atlanmis))
        self._review = None
        return {"ok": True, "yazilan": yazilan, "kural": kaydedilen,
                "cikti": self._cikti}

    def review_iptal(self) -> dict:
        self._review = None
        self._onizlemeyi_kapat()
        self._gecmis_kaydet(0, len(self._atlanmis))
        return {"ok": True, "cikti": self._mevcut_cikti()}

    def _onizlemeyi_kapat(self):
        """Açık PDF'i bırak — yoksa MuPDF dosyayı süreç boyunca kilitli tutar
        ve kullanıcı o faturayı Explorer'da taşıyamaz/silemez."""
        if self._pdf_doc is not None:
            try:
                self._pdf_doc.close()
            except Exception:
                pass
            self._pdf_doc = None
            self._pdf_yol = None

    def onizleme(self, i: int, sayfa: int, zoom: float) -> dict:
        """Faturanın PDF sayfasını PNG olarak döndürür (base64)."""
        satir = self._satir(i)
        if satir is None:
            return {"hata": "Önizleme yok"}
        yol = str(satir.get("dosya_yolu") or "")
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
        satir = self._satir(i)
        if satir is None:
            return False
        yol = str(satir.get("dosya_yolu") or "")
        if yol and os.path.exists(yol):
            os.startfile(yol)
            return True
        return False

    def gecmis(self) -> list:
        try:
            kayitlar = json.loads(self._gecmis.read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return list(reversed(kayitlar[-20:]))

    # ── İç yardımcılar ───────────────────────────────────────────────

    def _ayar_yaz(self, anahtar: str, deger: str) -> bool:
        try:
            set_key(str(self._env), anahtar, deger)
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
        try:
            self._pompa_dongusu()
        except Exception as e:
            # Pompa ölürse terminal olay hiç gitmez ve arayüz sonsuza dek
            # "işleniyor"da kalır; kullanıcının tek çıkışı uygulamayı kapatmak.
            self._js("olaylar", [{"t": "bitti", "hata": f"Beklenmedik hata: {e}",
                                  "yazilan": 0, "atlanan": len(self._atlanmis),
                                  "cikti": self._mevcut_cikti()}])
        finally:
            self._calisiyor = False

    def _pompa_dongusu(self):
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
        """Kapanışta işlemi durdur ve pencere boyutunu sakla (main.py'de
        closing'e bağlanır)."""
        # ThreadPoolExecutor thread'leri daemon değil: sinyal verilmezse Python
        # çıkmadan önce kuyruktaki her faturayı görünmeden Gemini'ye gönderir.
        self._stop_event.set()
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
        baska_nolar = self._baska_nolar()
        satirlar = []
        for i, satir in enumerate(payload["yeni"]):
            yol = str(satir.get("dosya_yolu") or "")
            satirlar.append({
                "i":        i,
                "form":     satir_form_degerleri(satir, self._sema),
                "uyarilar": veri_dogrula(satir, baska_nolar, self._sema),
                "dosya":    fatura.dosya_adi(satir),
                "pdf":      yol.lower().endswith(".pdf") and os.path.exists(yol),
                "kaynak":   fatura.kaynak(satir),
            })
        return {"t": "review", "satirlar": satirlar,
                # Alan adı/etiketleri Python'dan gelir; arayüz yalnızca
                # gruplamayı bilir, yeni alan eklenirse kendiliğinden görünür.
                "alanlar": [list(a) for a in self._sema.duzenlenebilir],
                "mevcut_sayi": len(payload["mevcut"]),
                "kesildi": payload.get("kesildi", False),
                # Koşu düzeyinde uyarı; satırların (alan, mesaj) sözleşmesinin dışında.
                "sema_farki": payload.get("sema_farki"),
                "atlanan": len(payload["atlanmis"])}

    def _kurallari_ogren(self, satirlar: list, hatirla: list,
                         haric: set) -> int:
        """'Firma için hatırla' işaretli satırlardan VKN bazlı kural üretir."""
        kurallar = kurallari_oku(self._duzeltme)
        eklenen = 0
        for i in {int(x) for x in (hatirla or [])} - haric:
            if i >= len(satirlar):
                continue
            vkn = str(satirlar[i].get("vkn") or "").strip()
            alanlar = ogrenilecek_alanlar(satirlar[i], self._sema)
            if vkn and alanlar:
                kurallar = kural_ekle(kurallar, vkn, alanlar, self._sema)
                eklenen += 1
        if eklenen:
            # Excel bu noktada yazılmış: hata JS'e kaçarsa onay akışı yarıda
            # kalır. TypeError/ValueError = JSON'a yazılamayan değer.
            try:
                kurallari_yaz(self._duzeltme, kurallar)
            except (OSError, TypeError, ValueError):
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
            gecmis = json.loads(self._gecmis.read_text("utf-8")) \
                     if self._gecmis.exists() else []
        except (OSError, ValueError):
            gecmis = []        # dosya kilitli/bozuk: geçmişi atla, işlemi bozma
        if not isinstance(gecmis, list):
            gecmis = []
        gecmis.append(kayit)
        try:
            self._gecmis.write_text(
                json.dumps(gecmis[-100:], ensure_ascii=False, indent=2), "utf-8")
        except OSError:
            pass
