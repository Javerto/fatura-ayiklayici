# Devir notu — Aday 02: Fatura değeri

Yeni bir oturumda bu işe buradan devam edilecek. Önceki oturum `gemini.py`
dikişini (Aday 01) tamamladı; bu belge Aday 02'yi devrediyor.

**Önce oku:** `CONTEXT.md` (alan sözlüğü), `CLAUDE.md` (proje kuralları).

---

## Bağlam: ne bitti

Mimari inceleme altı aday çıkardı; **Aday 01** (model çağrısını bir dikişin
ardına almak) bitti ve commit'lendi:

| Commit | |
|---|---|
| `e1c91e3` | `CONTEXT.md` alan sözlüğü + `GEMMA_MODEL` doğrulandı |
| `ed8ecfa` | Karakterizasyon testleri (`tests/test_gemini.py`) |
| `ba770de` | İstisnalar `hatalar.py`'ye |
| `a76d9f4` | Model çağrısı `gemini.py` dikişinin ardına |

Bugünkü modül düzeni: `gemini.py` (model adaptörü), `hatalar.py` (istisnalar),
`extraction.py` (çıkarım + saf mantık), `worker.py`, `review.py`, `duzeltme.py`,
`ozet.py`, `excel_utils.py`, `api.py`. Test sayısı **165**, hepsi yeşil.

> Aynı oturumda durum kartı arayüzü de yenilendi (commit `eb16bf6`). Aday 02 ile
> ilgisi yok, bu belgede yok sayılabilir.

---

## Aday 02: sorun

Sistemin merkezî kavramı — **bir fatura satırı** — hiçbir yerde tanımlı değil.
Sekiz modül aynı `dict`'i string anahtarla eşeliyor. İki somut kanıt:

### 1. Aynı türetme dört yerde kopyalanmış

`kaynak` alanı (`Dijital` / `OCR` / `XML`) her tüketicide yeniden hesaplanıyor:

```
worker.py:121          veri.get("_teknik_bilgi") or ("XML" if …endswith(".xml") else "")
api.py:422             satir.get("_teknik_bilgi") or ("XML" if …endswith(".xml") else "")
excel_utils.py:230     s.get("_teknik_bilgi") or ("XML" if …endswith(".xml") else "")
ozet.py:31-38          aynı kural, üstünde "excel_utils'teki kuralla aynı" yorumu
```

`ozet.py:31`'deki yorum kuralın kopyalandığını açıkça itiraf ediyor. Aynı şekilde
`os.path.basename(dosya_yolu)` da birden çok yerde tekrarlanıyor.

### 2. Alan listesi beş parçaya bölünmüş

```
extraction.py:20    PROMPT_SABLON            — modelden hangi alanlar istenecek
excel_utils.py:14   SUTUN                    — Excel sütun sırası
review.py:8         DUZENLENEBILIR_ALANLAR   — form alanları + tip + etiket
duzeltme.py:12      OGRENILEN_ALANLAR        — VKN bazlı öğrenilebilir alanlar
extraction.veri_dogrula                      — uyarı üreten alan adları
```

`tests/test_review.py:79` bu listelerden ikisinin senkron kalmasını *test ile*
zorluyor — eksik bir modülün tipik izi: testin görevi kayıp değişmezi ayakta
tutmak. Yeni bir alan eklemek bugün beş dosyaya dokunmak demek.

## Aday 02: önerilen yön

Bir **Fatura** modülü: alanlar + türetilmiş özellikler (`kaynak`, `dosya_adi`),
ve alan meta verisinin (anahtar, etiket, tip, Excel sütunu, öğrenilir mi) **tek**
bir tabloda toplanması. `SUTUN` ve `DUZENLENEBILIR_ALANLAR` o tablodan türetilir.
Excel'den okuma ile modelden çıkarma iki *adaptör* olur; ikisi de aynı Fatura'yı
üretir.

**Silme testi:** modülü silersen dört türetme geri dağılır ⇒ karmaşıklık
*toplanıyor*, sadece yer değiştirmiyor. Modül hak edilmiş.

---

## Karara bağlanacaklar (grilling ile)

Bunlar **kullanıcının** kararları, varsayma — tek tek sor, her soruda kendi
önerini de ver:

1. **Taşıyıcı tip ne olsun?** `@dataclass` mı, `TypedDict` mi, `dict` + saf
   yardımcı fonksiyonlar mı? (dataclass en çok şey verir ama JSON sınırında ve
   `excel_utils` içinde en çok dokunuşu gerektirir.)
2. **Kapsam:** yalnızca türetmeleri mi toplayalım (`kaynak`, `dosya_adi`), yoksa
   alan meta tablosunu da mı? İkincisi çok daha büyük diff.
3. **Sınırlar:** Fatura nesnesi nereye kadar gider? `api.py` arayüze zaten metin
   izdüşümü gönderiyor (`satir_form_degerleri`); Excel'e yazarken `dict`'e mi
   dönsün, yoksa `excel_utils` Fatura mı alsın?
4. **`_teknik_bilgi` adı:** alan adı `_` ile başlıyor ama Excel'e yazılıyor ve
   `mevcut_verileri_oku` geri okuyor. `kaynak` olarak yeniden adlandırılsın mı?
   (Geriye dönük uyumluluk: eski Excel dosyaları okunmaya devam etmeli.)
5. **Adım bölme:** tek seferde mi, yoksa "önce türetmeler, sonra meta tablo,
   sonra adaptörler" diye mi?

## Yöntem (önceki oturumda işe yaradı, aynen sürdür)

- **Önce karakterizasyon testi, sonra taşıma.** Mevcut davranışı bugünkü koda
  karşı çivile, yeşil gör, taşı, aynı iddiaların yeşil kaldığını göster.
- **Testin gerçekten tuttuğunu mutasyonla doğrula:** hatayı geri koy, kırmızıya
  döndüğünü gör, geri al. (CLAUDE.md'nin kuralı; `gemini.py` işinde 3 test
  kırmızıya döndü ve bu testlere güveni kurdu.)
- **Küçük commit'ler**, her biri kendi başına yeşil.
- **Veri güvenliği kuralları pazarlığa kapalı** — CLAUDE.md'deki
  "Data-safety rules" bölümü. Özellikle: `wb["Faturalar"]` (asla `wb.active`),
  `_guvenli_kaydet`, okunamayan Excel'de *fırlat*, gizli yol sütununun yeri.
  Fatura'ya geçiş bunların hiçbirini bozmamalı.
- Arayüze dokunulursa: **önce atılabilir HTML mockup**, sonra kod; ve
  **uygulamayı çalıştırıp kullanıcıya baktır** — arayüz hataları pytest'te
  görünmüyor.

## Doğrulama

```bash
python -m pytest -q        # 165 test, hepsi yeşil olmalı
```

Bu işte özellikle şu testler bekçi: `tests/test_excel_kaynak.py` (Kaynak sütunu
gidiş-dönüşü), `tests/test_excel_guvenlik.py` (veri kaybı kuralları),
`tests/test_ozet.py`, `tests/test_olay_sozlesmesi.py` (Python↔JS anahtarları),
`tests/test_review.py:79` (alan adı senkron bekçisi — Aday 02 bunu gereksiz
kılmalı).

## Kalan adaylar (bu işten sonra)

- **03** — "hangi dosyalar işlenecek" kuralı `worker.py` ve `api.klasor_ozeti`'nde
  iki farklı şekilde yazılmış. ~30 satır, ucuz, davranışı değiştirmez.
- **04** — `Api` sığ kabuk; altında yazılı olmayan bir durum makinesi var.
- **05** — `excel_utils` hem arşiv hem rapor biçimlendiricisi.
- **06** — Ayarlar `os.environ` üzerinden akıyor (spekülatif).
