"""Kod tabanı kuralları: CLAUDE.md, docs/arayuz.md ve CODING_STANDARDS.md'deki
mekanik kurallar burada denetlenir. Muhakeme isteyenler CODING_STANDARDS.md'de."""
import ast
import pathlib
import re

KOK = pathlib.Path(__file__).resolve().parent.parent
WEB = KOK / "web"
MODULLER = sorted(KOK.glob("*.py"))


def _eslesen(desen, dosyalar):
    return [f"{p.name}:{i}: {s.strip()}"
            for p in dosyalar
            for i, s in enumerate(p.read_text("utf-8").splitlines(), 1)
            if re.search(desen, s)]


def test_tarayici_diyaloglari_kullanilmaz():
    """WebView2 confirm/alert'i "127.0.0.1:… diyor ki" başlığıyla açar.
    Yerine app.js'teki onayModal/bilgiModal."""
    assert _eslesen(r"(?<![\w.])(?:window\.)?(?:confirm|alert)\s*\(",
                    WEB.glob("*.js")) == []


def test_renk_sabit_yazilmaz():
    """Sabit renk altı temanın beşini bozar; tema.css değişkenleri kullanılır.
    tema.js'teki seçici önizleme renkleri bilinçli istisna."""
    # ponytail: yalnız hex yakalanır; rgb()/hsl() sabitleri de görülürse desen genişler.
    dosyalar = [p for p in WEB.iterdir()
                if p.suffix in (".css", ".js", ".html")
                and p.name not in ("tema.css", "tema.js")]
    assert _eslesen(r"#[0-9a-fA-F]{3,8}\b", dosyalar) == []


def test_fatura_sayfasi_wb_active_ile_okunmaz():
    """Excel son açık sekmeyi kaydeder; "Özet" açıkken kaydedilen dosyada
    wb.active faturaları değil özeti okur. Tek meşru kullanım: yeni Workbook()."""
    hatali = []
    for p in MODULLER:
        satirlar = p.read_text("utf-8").splitlines()
        for i, s in enumerate(satirlar):
            kod = s.split("#", 1)[0]
            if re.search(r"\.active\b", kod) and "Workbook()" not in satirlar[i - 1]:
                hatali.append(f"{p.name}:{i + 1}: {s.strip()}")
    assert hatali == []


def test_kaydetme_yalnizca_guvenli_kaydet_icinde():
    """Doğrudan save hedefi önce sıfırlar; yarıda kalan yazma arşivi siler.
    _guvenli_kaydet .tmp'ye yazıp os.replace eder."""
    hatali = []
    for p in MODULLER:
        agac = ast.parse(p.read_text("utf-8"))
        izinli = {id(d) for fn in ast.walk(agac)
                  if isinstance(fn, ast.FunctionDef) and fn.name == "_guvenli_kaydet"
                  for d in ast.walk(fn)}
        hatali += [f"{p.name}:{d.lineno}" for d in ast.walk(agac)
                   if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                   and d.func.attr == "save" and id(d) not in izinli]
    assert hatali == []
