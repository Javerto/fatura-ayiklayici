# Onay / Düzeltme Arayüzü — Tasarım Dokümanı

**Tarih:** 2026-06-08
**Durum:** Onaylandı (uygulama bekliyor)

## Amaç

Çıkarılan fatura verileri şu an doğrudan Excel'e yazılıyor; AI'ın yaptığı
hatalar (yanlış tutar, eksik VKN, okunamayan tarih) sessizce çıktıya gidiyor.
Bu özellik, **Excel yazılmadan önce** kullanıcıya bir gözden geçirme/düzeltme
adımı sunar: yeni faturalar bir tabloda gösterilir, uyarılı alanlar işaretlenir,
kullanıcı kaynak PDF'e bakarak alanları düzeltebilir, istemediği faturaları
hariç tutabilir ve ancak onayladıktan sonra Excel yazılır.

## Kapsam ve Kararlar

- **Zamanlama:** Tüm dosyalar işlendikten sonra, tek seferde, **tüm yeni
  faturalar** bir tabloda gösterilir (per-file değil). Her çalıştırmada açılır
  (yeni fatura varsa).
- **Düzen:** Master-detail — üstte özet tablo, bir satıra tıklayınca altta o
  faturanın tüm alanları form olarak açılır.
- **Yetenekler:** alan düzenleme, anlık uyarı yenileme, tüm 11 veri alanı
  düzenlenebilir, uyarılı satırlara hızlı atlama, satırı hariç tutma, ve
  **kaynak PDF'in gömülü önizlemesi** (+ ayrı pencerede açma).
- **Önizleme:** form yanında gömülü PDF render (fitz), zoom + sayfa gezme,
  ayrıca "Dışarıda Aç" butonu. XML-only/PDF yoksa "Önizleme yok".
- **Uygula:** alan değişiklikleri açık "Uygula" butonuyla işlenir (otomatik değil).
- **Mimari:** Sorumluluk ayrımı — saf mantık (`review.py`) + arayüz
  (`review_ui.py`) ayrı; worker Excel yazmaz, GUI onayda yazar.

## Veri Akışı

```
1. Kullanıcı klasör seçer → Başlat
2. Worker (thread): PDF/XML işler, her faturayı log'a basar (✓/⚠ — şimdiki gibi)
   • Excel yazımı YOK (ne "her 5'te bir" ne "sonda")
   • Yeni satırlar ayrı listede toplanır (yeni_satirlar)
3. İşlem bitince worker → kuyruğa ("review", payload) yollar
   payload = {mevcut, yeni, atlanmis, uyarilar, cikti, kesildi}
   (kesildi: bool — Durdur/API-key nedeniyle yarıda kesildiyse True)
   • Yeni satır yoksa: eskisi gibi ("done", ...) → review YOK
   • Durdur / API-key hatası olsa bile, başarılı satır varsa review açılır
4. GUI (_poll_queue) "review" olayını yakalar → ReviewWindow açılır (palet geçirilir)
5. Kullanıcı düzeltir / hariç tutar / onaylar
   • Onayla → excel_olustur(nihai_satirlar) → geçmiş kaydedilir → butonlar aktif
   • İptal   → hiçbir şey yazılmaz (onay diyaloğuyla)
6. Atlananlar → "Yeniden Dene", kalan uyarılar → "⚠ Uyarılar" (şimdiki gibi)
```

**Kenar durum:** Excel yazımı başarısız olursa (dosya açık → izin hatası), review
penceresi **kapanmaz**; hata gösterilir, kullanıcı Excel'i kapatıp tekrar
"Onayla" der — düzeltmeler kaybolmaz.

## Bileşenler

İki yeni dosya, iki değişiklik.

### 🆕 `review.py` — saf mantık (tkinter yok, tam test edilebilir)

```python
DUZENLENEBILIR_ALANLAR = [   # sıra + etiket + tip
    ("fatura_no",            "Fatura No",            "metin"),
    ("fatura_tarihi",        "Fatura Tarihi",        "tarih"),
    ("sirket_adi",           "Şirket Adı",           "metin"),
    ("vkn",                  "VKN",                  "metin"),
    ("vergi_dairesi",        "Vergi Dairesi",        "metin"),
    ("tanim",                "Tanım",                "metin"),
    ("toplam_miktar",        "Toplam Miktar",        "sayi"),
    ("kdv_haric_tutar",      "KDV Hariç Tutar",      "sayi"),
    ("vergiler_dahil_tutar", "Vergiler Dahil Tutar", "sayi"),
    ("para_birimi",          "Para Birimi",          "metin"),
    ("sira_no",              "Sıra No",              "sayi"),
]   # dosya_yolu + _teknik_bilgi salt-okunur (düzenlenmez)

def satir_form_degerleri(row: dict) -> dict[str, str]:
    """Satırı forma yazılacak metinlere çevirir.
    datetime→'GG.AA.YYYY', float→str, None→''."""

def form_satira_uygula(row: dict, form: dict[str, str]) -> dict:
    """Form metinlerini geri çevirip güncellenmiş satır döndürür.
    'tarih'→tarih_parse, 'sayi'→to_float, 'metin'→strip."""

def nihai_satirlar(mevcut: list, yeni: list, haric: set[int]) -> list:
    """Excel'e yazılacak nihai liste: mevcut + (haric olmayan yeni)."""
```

Yeniden doğrulama için mevcut `extraction.veri_dogrula` aynen kullanılır.

### 🆕 `review_ui.py` — `ReviewWindow(Toplevel)`

- Renk paletini **parametre olarak** alır (gui.py'den geçirilir → dairesel
  import yok).
- Bileşenler: Treeview özet tablo + düzenleme formu + gömülü PDF önizleme +
  alt buton çubuğu.
- GUI'ye `on_confirm(nihai_satirlar)` / `on_cancel()` geri-çağırımlarıyla bağlanır.
- PDF render: `fitz` pixmap → `pix.tobytes("png")` → `tk.PhotoImage(data=...)`
  (PIL gerekmez). Zoom = matrix yeniden render; sayfa gez = ilgili sayfa render.

### ✏️ `worker.py`

- `excel_olustur` çağrıları kaldırılır (her-5 ve final). `import` da kaldırılır.
- Yeni satırlar `yeni_satirlar` listesinde toplanır (mevcut `satirlar` mantığı
  mevcut + yeni olarak ikiye ayrılır).
- Sonda: yeni satır varsa `("review", payload)`; yoksa eskisi gibi `("done", ...)`.
- Durdur / API-key abort yollarında: kısmi `yeni_satirlar` varsa yine "review"
  (başlıkta yarıda kesildi notu için payload'a bir bayrak: `kesildi: bool`).

### ✏️ `gui.py`

- `_poll_queue`'ya `"review"` kolu: `ReviewWindow` açar, paleti (`_KARANLIK`/
  `_AYDINLIK` aktif değerleri) ve `cikti` yolunu geçirir.
- `on_confirm(nihai)` → `excel_olustur(nihai, cikti)` + geçmiş kaydet + buton
  durumları (eski "done" işleme mantığı buraya taşınır). Yazım hatası →
  messagebox, pencere açık kalır.
- `on_cancel()` → yazmadan kapanış; geçmiş islenen=0.

## Arayüz Düzeni

```
┌─ Faturaları Gözden Geçir — 3 yeni fatura, 2 uyarı ─────────────────┐
│ Fatura No          Şirket          Tutar    Kaynak  ⚠              │  Treeview
│ GIB2024000000123   ACME...         1.180    Dijital  -             │  (uyarılı=sarı,
│►ABC2024000000777   Eski Matbaa..     590    OCR      2  ◄ seçili   │   hariç=gri/çizili)
│ XYZ2024000000999   Veri Tek..      2.360    XML      -             │
├─ Düzenle ──────────────────────┬─ Önizleme ───────────────────────┤
│ Fatura No: [...]               │   ┌───────────────────┐          │
│ Tarih    : [02.04.2024]        │   │   PDF 1. sayfa     │          │
│ Şirket   : [...]               │   └───────────────────┘          │
│ ... (11 alan, kaydırılabilir)  │   [ − ] [ + ]  sayfa 1 / 2        │
│ ⚠ VKN ... (kırmızı)            │   [ Dışarıda Aç ]                 │
│        [ Uygula ]              │                                   │
├────────────────────────────────┴───────────────────────────────────┤
│ [☐ Bu faturayı hariç tut]  [◀ Önceki ⚠] [Sonraki ⚠ ▶]            │
│                                   [ İptal ]   [ Onayla & Excel ]    │
└─────────────────────────────────────────────────────────────────────┘
```

**Etkileşim kuralları:**
- Satır seç → form dolar + PDF önizleme yüklenir.
- **Uygula** → `form_satira_uygula` + `veri_dogrula` tekrar koşar; Treeview'deki
  Tutar/⚠ ve formdaki uyarılar anında yenilenir.
- **Hariç tut** → satır nihai listeden çıkar; Treeview'de gri/üstü çizili.
- **Önceki/Sonraki ⚠** → uyarılı bir sonraki satıra atlar; açılışta otomatik ilk
  uyarılı satır seçili gelir.
- Önizleme: `−/+` zoom, sayfa gez, **Dışarıda Aç** → `os.startfile(pdf)`.
  PDF yok/XML → "Önizleme yok".
- Tarih/sayı alanları metin olarak düzenlenir; Uygula'da çevrilir.
- CLAUDE.md kuralı: `OptionMenu` kullanılmaz, renkler sabit-kodlanmaz.

## Hata Yönetimi & Kenar Durumlar

| Durum | Davranış |
|-------|----------|
| Excel yazılamıyor (dosya açık) | messagebox; **review penceresi kapanmaz**, tekrar "Onayla" denenebilir |
| PDF render başarısız | "Önizleme yüklenemedi"; çökmez |
| XML-only / PDF yok | "Önizleme yok"; "Dışarıda Aç" pasif |
| Geçersiz tarih | `tarih_parse` metni döndürür → "Tarih okunamadı" uyarısı; yazımı engellemez |
| Geçersiz sayı | `to_float`→None → ilgili uyarı; yazımı engellemez |
| Onayla'da hâlâ uyarı | Yumuşak onay: "N faturada hâlâ uyarı var, yine de yazılsın mı?" |
| İptal / pencere X | Onay: "Çıkarılan veriler ve düzeltmeler kaydedilmeyecek. Emin misiniz?" |
| Tüm satırlar hariç | Yazılacak yeni satır yok; bilgi verir, Excel'e dokunmaz |
| Yeni satır yok | Worker "review" yollamaz; pencere açılmaz |
| Durdur / API-key hatası + kısmi başarı | Başarılı satırlar review'a gelir; başlıkta "(yarıda kesildi)" |

**İlke:** Uyarılar yazımı **engellemez**, sadece bilgilendirir (mevcut
`veri_dogrula` felsefesi). Tek sert durdurucu: dosya kilitli olunca yazamama.

## Test Stratejisi

TDD, mevcut 63 testin üstüne.

**`tests/test_review.py` — saf birim testleri:**
- `satir_form_degerleri`: datetime/float/None → metin dönüşümü.
- `form_satira_uygula`: tarih metni→datetime, geçersiz tarih→metin; sayı
  ("1.234,56")→float, geçersiz→None; boş→None/"".
- **Yeniden doğrulama kapanışı:** hatalı VKN'li satır uyarı verir; VKN
  düzeltilip `form_satira_uygula` sonrası `veri_dogrula` uyarısı kalkar.
- `nihai_satirlar`: hariç indeksler çıkar, `mevcut` korunur, sıra doğru.

**`tests/test_worker.py` — sözleşme güncellemesi:**
- ⚠️ Mevcut test "worker Excel yazar" varsayıyor → artık yazmamalı.
  - XML-only klasör → `("review", payload)`, `payload["yeni"]` 1 fatura,
    **worker Excel dosyası oluşturmaz**.
  - Boş klasör → `("critical", ...)`.
  - Hepsi işlenmiş → `("done", ...)`, review yok.

**`review_ui.py` — görsel/smoke:**
- Örnek payload ile `ReviewWindow` kurulum smoke (render → ekran görüntüsü →
  kapat). Tam etkileşim manuel test.

**Regresyon:** `python -m pytest` tamamı yeşil; `excel_utils`/`extraction`
testleri etkilenmez.

## Kapsam Dışı (sonraya)

- Onay adımını aç/kapa eden bir ayar (şimdilik her zaman açık).
- Öğrenen düzeltmeler / tedarikçi başına kural hafızası.
- Toplu düzenleme (birden çok satıra aynı değer).
