# Tutar Tutarlılık Kontrolü + Özet Sayfası — Tasarım

**Tarih:** 2026-06-10
**Durum:** Onaylandı (kullanıcı, sohbet içinde)

## Amaç

İki tamamlayıcı özellik:

1. **Tutar tutarlılık kontrolü** — AI'ın (veya XML'in) tutar hatalarını matematiksel
   olarak yakalar: "KDV hariç + KDV = vergiler dahil" ilişkisi bilinen KDV
   oranlarına uymuyorsa uyarı üretir. Uyarı, mevcut `veri_dogrula` akışıyla
   gözden geçirme penceresine düşer.
2. **Özet sayfası** — Çıktı Excel'ine otomatik bir "Özet" sayfası ekler: genel
   toplamlar, aylık kırılım ve şirket kırılımı. Muhasebeye hazır rapor.

## Kapsam Dışı (YAGNI)

- Döviz kuru çevirisi (para birimleri ayrı toplanır, çevrilmez).
- Tevkifat/özel matrah hesaplama — bunlar yalnızca uyarı olarak görünür.
- Excel formülleriyle "canlı" özet (statik değerler yazılır; dosya her işlemde
  uygulama tarafından yeniden üretildiği için canlı formülün faydası yok).
- Grafik/pivot.

## 1. Tutar Tutarlılık Kontrolü

**Yer:** `extraction.py` → `veri_dogrula` içine yeni blok (saf mantık).

**Kural:** `kdv_haric_tutar` (H) ve `vergiler_dahil_tutar` (D) **ikisi de dolu
ve > 0** ise:

- `D < H` → uyarı: `"Vergiler dahil tutar (D) KDV hariç tutardan (H) küçük"`.
- Aksi halde örtük KDV oranı hesaplanır: `oran = (D - H) / H * 100`.
  Oran, bilinen Türkiye KDV oranlarından (`0, 1, 8, 10, 18, 20`) birine
  **±0,5 puan** toleransla uymuyorsa → uyarı:
  `"Örtük KDV oranı %X,X bilinen oranlara (0/1/8/10/18/20) uymuyor — tutarları kontrol edin"`.
- Alanlardan biri boş/None ya da ≤ 0 ise kontrol **atlanır** (mevcut "tutar boş"
  uyarıları zaten var; çifte uyarı üretilmez).

**Notlar:**

- %0 KDV (D == H) geçerlidir — tolerans bunu kapsar.
- Bilinen oranlar modül sabiti olarak tanımlanır: `KDV_ORANLARI = (0, 1, 8, 10, 18, 20)`.
- Tevkifatlı/özel faturalarda yanlış alarm olabilir; bu bilinçli bir tercih —
  uyarı engelleyici değildir, gözden geçirme penceresinde görünür ve kullanıcı
  yine de onaylayabilir.
- Kullanıcı gözden geçirme penceresinde tutarı düzeltip "Uygula" dediğinde
  `veri_dogrula` yeniden çalıştığı için uyarı otomatik kalkar (ek kod gerekmez).

## 2. Özet Sayfası

### 2a. Saf hesap: `ozet.py` (yeni modül, tkinter'sız)

```python
ozet_hesapla(satirlar: list[dict]) -> dict
```

Dönen yapı üç blok içerir:

- **`genel`**: toplam fatura adedi; para birimi bazında toplam tutar
  (`vergiler_dahil_tutar`) ve toplam KDV; kaynak dağılımı
  (`Dijital` / `OCR` / `XML` / boş → `Bilinmiyor` adetleri).
- **`aylik`**: `"YYYY-AA"` anahtarıyla kronolojik sıralı; her ay için adet ve
  para birimi bazında toplam tutar. `fatura_tarihi` datetime değilse satır
  `"Bilinmiyor"` anahtarına gider (en sonda gösterilir).
- **`sirket`**: `sirket_adi` bazında (boş → `"Bilinmiyor"`); adet ve para
  birimi bazında toplam tutar; toplam tutara göre azalan sıralı.

**Kurallar:**

- KDV tutarı = `vergiler_dahil_tutar - kdv_haric_tutar`, yalnızca ikisi de
  sayısal ve doluysa; değilse o satır KDV toplamına katılmaz (tutar toplamına
  katılır).
- Para birimi boş/None ise `"TL"` varsayılır (mevcut veride baskın durum).
- Tutar alanı sayısal değilse (örn. None) o satır tutar toplamına katılmaz ama
  adetlerde sayılır.

### 2b. Excel yazımı: `excel_utils.excel_olustur` içinde

- Ana veri sayfası yazıldıktan sonra: çalışma kitabında `"Özet"` adlı sayfa
  varsa **silinir**, `ozet_hesapla` sonucuyla yeniden oluşturulur (ikinci
  yazımda çoğalma/bayatlama olmaz).
- "Özet" **ikinci sayfa** olur; ana veri sayfası ilk ve aktif sayfa kalır —
  `mevcut_verileri_oku` ve eski çıktıların okunabilirliği etkilenmez.
- Stil: mevcut başlık stiliyle aynı (lacivert dolgu `2F5496`, beyaz kalın
  Arial); üç blok alt alta, aralarında boş satır; tutar hücreleri
  `#,##0.00` formatlı.
- Çok para birimli toplamlar ayrı satırlarda gösterilir
  (örn. `Toplam Tutar (TL)` ve `Toplam Tutar (EUR)` ayrı satırlar).

## Veri Akışı

Değişmez: worker → `("review", payload)` → ReviewWindow → onay →
`excel_olustur(nihai, ...)`. Özet, `excel_olustur` çağrısının içinde nihai
satır listesinden hesaplanır; tutar kontrolü `veri_dogrula` üzerinden hem
worker'da hem review "Uygula"sında otomatik çalışır. GUI/worker/review
kodunda değişiklik **yoktur**.

## Hata Yönetimi

- `ozet_hesapla` saf hesaptır; bozuk satır alanları (None, yanlış tip) kuralla
  tolere edilir, istisna fırlatmaz.
- Özet yazımı `excel_olustur`'un mevcut hata akışına dahildir (dosya kilitliyse
  zaten `ExcelHatasi` yükselir; ana veri ile özet aynı kaydetme işleminde yazılır).

## Test Planı (pytest, tkinter'sız)

**`veri_dogrula` (tests/test_dogrulama.py veya mevcut dosyaya ek):**

- %20 KDV'li doğru fatura (H=100, D=120) → tutar uyarısı yok.
- D < H (H=120, D=100) → "küçük" uyarısı.
- Saçma oran (H=100, D=137) → "örtük KDV oranı" uyarısı.
- %0 KDV (H=100, D=100) → uyarı yok.
- %1 ve %10 sınır değerleri toleransla geçer.
- H boş veya D boş → tutar tutarlılık uyarısı üretilmez.

**`ozet_hesapla` (tests/test_ozet.py):**

- Çok para birimli satırlar → para birimi bazında ayrı toplamlar.
- Tarihsiz satır → aylıkta "Bilinmiyor".
- Şirket sıralaması toplam tutara göre azalan.
- KDV alanı eksik satır → KDV toplamına girmez, adette sayılır.
- Boş liste → istisnasız boş yapı.

**Excel round-trip (tests/test_excel.py'ye ek):**

- Özet sayfalı dosyada `mevcut_verileri_oku` ana veriyi doğru okur.
- İkinci `excel_olustur` çağrısında "Özet" sayfası tek kalır ve güncellenir.
- Ana sayfa ilk/aktif sayfa olmaya devam eder.
