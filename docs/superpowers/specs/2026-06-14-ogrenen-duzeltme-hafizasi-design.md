# Öğrenen Düzeltme Hafızası — Tasarım

**Tarih:** 2026-06-14
**Durum:** Onaylandı

## Amaç

Review penceresinde firma-sabit bir alan düzeltilip "hatırla" işaretlendiğinde, o firmanın **VKN'sine** bağlı bir kural kaydedilir. Sonraki çalıştırmalarda aynı VKN'li faturalar çıkarıldığında bu alanlar otomatik düzeltilir — kullanıcı zamanla daha az düzeltme yapar.

Bu, son eklenen review/onay arayüzünün (bkz. `2026-06-08-onay-duzeltme-arayuzu-design.md`) doğal devamıdır: review penceresi *yeni* faturaları yazmadan önce düzeltmeyi sağlar; bu özellik o düzeltmeleri *kalıcı* hale getirip tekrarını önler.

**Öğrenilen alanlar:** `sirket_adi`, `vergi_dairesi`.
VKN eşleştirme anahtarı olduğu için kendisi öğrenilmez. `para_birimi` bilinçli olarak **kapsam dışı** bırakıldı (bkz. Tasarım Kararları).

## Tasarım Kararları (brainstorming özeti)

- **Kapsam:** Yalnızca firma kimliğine ait, değişmez alanlar (`sirket_adi`, `vergi_dairesi`). Faturaya özel alanlar (`fatura_no`, `fatura_tarihi`, tutarlar, `tanim`, `sira_no`) öğrenilemez çünkü her faturada farklıdır; "geçen sefer şuydu" bilgisi genellenemez.
- **`para_birimi` neden kapsam dışı:** Aynı firma yurt içinde TL, ihracatta EUR/USD kesebilir; para birimi faturaya özeldir, firma-sabit değildir. Yanlış öğrenilen bir para birimi, doğru çıkarılmış bir değeri sessizce ezebilir — kazanımdan büyük bir risk. Bu yüzden öğrenilen alanların dışında tutuldu.
- **Mekanizma:** Deterministik post-processing kuralları — AI prompt'una **dokunulmaz**. Prompt güncelleme reddedildi (tavuk-yumurta firma tespiti, çift API çağrısı maliyeti, deterministik olmama, test edilemezlik, sınırsız prompt büyümesi).
- **Kayıt şekli:** Açık onay — review formunda checkbox. Tek seferlik düzeltme istemeden kalıcı kural olmaz.
- **Eşleştirme:** VKN ile. AI şirket adını yeni bir yanlış varyasyonla yazsa bile VKN aynıysa düzeltilir.

## Bileşenler

### 1. `duzeltme.py` (yeni, saf mantık — tkinter/Excel'siz)

- `kurallari_oku(yol) -> dict` — JSON oku; dosya yok/bozuksa `{}` döndür (çökme yok).
- `kurallari_yaz(yol, kurallar)` — JSON yaz.
- `kural_uygula(satir, kurallar) -> dict` — satırın `vkn`'si bir kuralla eşleşirse firma-sabit alanları geçersiz kılınmış bir **kopya** döndürür; eşleşme yoksa kopyayı olduğu gibi döndürür. Saf fonksiyon (orijinali bozmaz).
- `kural_ekle(kurallar, vkn, alanlar) -> dict` — yeni düzeltmeyi kurallara birleştirip güncel kopya döndürür; boş/None değerleri atlar.
- Sabit: `OGRENILEN_ALANLAR = ["sirket_adi", "vergi_dairesi"]`.

### 2. `worker.py`

- `worker(...)` imzasına `kurallar: dict | None = None` parametresi eklenir (varsayılan `{}`).
- `islendi(veri)`'nin başında `veri = kural_uygula(veri, kurallar)` çağrılır.
- Böylece düzeltilmiş değerler hem log satırına, hem `yeni_satirlar`'a, hem de `veri_dogrula` uyarılarına yansır.

### 3. `review_ui.py` / `review.py`

- Forma **"☐ Bu düzeltmeleri [Firma] için hatırla"** checkbox'ı eklenir.
- "Uygula"ya basıldığında kutu işaretliyse, o satırın VKN'si + firma-sabit değerleri toplanır (`{vkn: {alanlar}}`).
- Onayda toplanan kurallar dışarı verilir. `on_confirm` imzası `(nihai, uyarilar, yeni_kurallar) -> bool` olarak genişler.
- **VKN boşsa** checkbox pasif/uyarılı olur (VKN'siz kural kaydedilemez).

### 4. `gui.py`

- `duzeltmeler.json` AppData-duyarlı yoldan okunur (`.env`/`gecmis.json` ile aynı desen: frozen modda `%APPDATA%\FaturaAyiklayici`, değilse proje klasörü).
- Okunan kurallar worker'a geçirilir.
- Onayda yeni kurallar mevcutlarla birleştirilip dosyaya yazılır (Excel yazımıyla aynı akışta).

## Veri Akışı

1. Worker `kurallar`'ı alır → her çıkarılan satıra `kural_uygula` → `veri_dogrula` düzeltilmiş değerlerle çalışır → review payload'u düzeltilmiş satırlarla dolar.
2. Kullanıcı review'da kalanları düzeltir, istediği firmalar için "hatırla" işaretler → `{vkn: {alanlar}}` toplanır.
3. Onayda: Excel yazılır (mevcut akış) **+** yeni kurallar `duzeltmeler.json`'a kaydedilir.

## Depolama (`duzeltmeler.json`)

```json
{
  "1234567890": {
    "sirket_adi": "ARÇELİK A.Ş.",
    "vergi_dairesi": "Büyük Mükellefler"
  }
}
```

VKN string anahtardır. Yalnızca dolu firma-sabit değerler saklanır (kısmi profil olabilir).

## Hata / Sınır Durumları

- Yeni faturada VKN yok/eşleşmiyor → kural uygulanmaz, zarar yok.
- Bozuk/eksik JSON → `{}` kabul, çökme yok.
- **VKN'nin kendisi yanlışsa** → VKN anahtar olduğu için öğrenilemez (tavuk-yumurta); o sefer elle düzeltilir. *(Bilinen sınır.)*

## Test (saf-mantık odaklı, mevcut kültüre uygun)

- `duzeltme.py`: oku/yaz/uygula/ekle — eşleşme, eşleşmeme, boş VKN, bozuk JSON, kopya-bütünlüğü (orijinali bozmama).
- `worker.py`: kural verilince satırın düzeltilmesi ve uyarıların düzeltilmiş değere göre hesaplanması.
- `review.py`: "hatırla" işaretliyken kuralın toplanması, VKN boşken toplanmaması.
