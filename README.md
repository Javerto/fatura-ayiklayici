# Fatura Ayıklayıcı (Invoice Extractor)

Türkçe PDF ve XML e-faturalarından otomatik veri çıkarma uygulaması. Google Gemini AI kullanarak fatura bilgilerini okur, siz onayladıktan sonra düzenli bir Excel dosyasına aktarır.

## 🚀 Özellikler

- **Hibrid PDF İşleme:** Dijital PDF'lerde doğrudan metin üzerinden, taranmış (resim) PDF'lerde ise OCR (Vision) üzerinden veri ayıklar.
- **XML Desteği:** UBL formatındaki e-faturaları (XML) doğrudan ve hatasız ayrıştırır.
- **Onay Ekranı:** Çıkarılan veriler **doğrudan Excel'e yazılmaz.** Önce gözden geçirme ekranı açılır; faturaları düzeltir, gerekirse hariç tutar, sonra onaylarsınız. İptal ederseniz hiçbir şey yazılmaz.
- **Öğrenen Düzeltmeler:** Bir firmanın adını veya vergi dairesini düzeltirken "bu firma için hatırla" derseniz, aynı VKN'li sonraki faturalarda otomatik uygulanır.
- **Veri Uyarıları:** Fatura no uzunluğu, VKN biçimi, boş tarih ve tutarlar arasındaki KDV oranı tutarlılığı kontrol edilir. Uyarılar, ait oldukları alanın altında gösterilir.
- **Paralel İşleme:** PDF dosyalarını 5 iş parçacığı (thread) ile işler; ücretsiz kotayı aşmamak için dakikada 14 istekle sınırlar.
- **Akıllı Excel Çıktısı:** Kaynak dosyalara tıklanabilir bağlantılar, her satırın hangi yolla okunduğunu (Dijital/OCR/XML) gösteren "Kaynak" sütunu ve otomatik **Özet sayfası** (aylık ve firma bazlı, para birimi ayrımıyla).
- **Artımlı Çalışma:** Daha önce işlenmiş faturaları algılar ve atlar, sadece yeni eklenenleri işler.

## 🖥️ Arayüz

Arayüz **pywebview** penceresinde çalışan HTML/CSS/JS'tir; Python tüm mantığı elinde tutar, tarayıcı yalnızca görüntüleme katmanıdır. Windows'un hazır **WebView2** bileşenini kullanır, ayrıca bir tarayıcı kurulumu gerektirmez.

- **Tek pencere.** Gözden geçirme ekranı ayrı bir pencere açmaz, ana ekranın yerine geçer.
- **Altı tema:** Mocha (varsayılan), Macchiato, Frappé, Nord (koyu) ve Latte, Kağıt (açık). Seçim `.env`'e kaydedilir.
- **Boyutlandırılabilir pencere;** boyut hatırlanır. (Konum bilinçli olarak saklanmaz — uzak masaüstünde çözünürlük değişince pencere ekran dışında kalabiliyor.)
- **Gözden geçirme ekranı üç sütunlu:** solda fatura listesi, ortada düzenleme formu, sağda kaynak PDF önizlemesi (yakınlaştırma ve sayfa gezinme ile). Pencere daraldığında önizleme kapanır.
- Formda **"Uygula" butonu yoktur** — alandan çıktığınızda değişiklik uygulanır ve uyarılar tazelenir.

## 🛠️ Kurulum

### 1. Gereksinimler
- Python 3.11 veya üzeri
- Windows (WebView2 bileşeni; Windows 10/11'de Edge ile birlikte kurulu gelir)
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/)'dan ücretsiz alabilirsiniz)

### 2. Bağımlılıkları Yükleme
```bash
pip install -r requirements.txt
```

### 3. Yapılandırma
- Proje klasöründeki `.env.example` dosyasının adını `.env` olarak değiştirin.
- İçindeki `GEMINI_API_KEY` kısmına kendi API anahtarınızı yapıştırın.

*(Not: Uygulama ilk açılışta API key girilmemişse size otomatik olarak soracaktır. EXE olarak çalışırken ayarlar `%APPDATA%\FaturaAyiklayici` altında tutulur.)*

## 📖 Kullanım

### Geliştirme Modunda Çalıştırma
```bash
python main.py
```

### Adımlar
1. **Klasör Seç:** Faturalarınızın (PDF/XML) bulunduğu klasörü seçin. Son kullandığınız klasör hatırlanır.
2. **Başlat:** Durum kartından ilerlemeyi, kalan süreyi ve başarılı/uyarılı/atlanan dağılımını takip edin.
3. **Gözden Geçir:** İşlem bitince onay ekranı açılır. Uyarılı faturaları düzeltin, istemediklerinizi hariç tutun.
4. **Onayla:** Excel yazılır. **Onaylayana kadar dosyaya dokunulmaz.**

### Testler
```bash
python -m pytest
```

### EXE Olarak Derleme (Windows)
```bash
build.bat
```
Çıktı `dist/FaturaAyiklayici.exe` olarak oluşur (~44 MB). Betik temiz bir sanal ortam kurar, `web/` klasörünü EXE'nin içine paketler ve geçici dosyaları temizler.

## ⚙️ Özelleştirme

### Alanlar ve Prompt
Hangi alanların çıkarılacağı `alanlar.json` dosyasındadır (EXE'de `%APPDATA%\FaturaAyiklayici`, geliştirmede proje kökü; ilk açılışta kendiliğinden oluşur). Yeni alan için listeye `{"etiket": "Sipariş No", "tip": "metin", "aciklama": "..."}` ekleyin — `anahtar` ve `sutun` uygulama tarafından atanır. Model promptu, Excel sütunları ve gözden geçirme formu bu dosyadan türetilir; promptun sabit yönerge başlığı `sema.py` içindeki `PROMPT_BASLIK`'tadır.

### Model ve Kota Ayarları
Modelle ilgili her sabit `gemini.py` içindedir: `GEMMA_MODEL`, `MAX_DENEME`, `TIMEOUT_SANIYE`, `RPM_LIMIT`, `THINKING_BUDGET`.

### Tema Ekleme
`web/tema.css` içindeki bir tema bloğunu kopyalayıp renkleri değiştirin, `web/tema.js` içindeki `TEMALAR` listesine ekleyin. Başka dosyaya dokunmanız gerekmez.

## 📂 Proje Yapısı

| Dosya | Sorumluluk |
|---|---|
| `main.py` | Giriş noktası; pywebview penceresini açar |
| `api.py` | Arayüz ↔ Python köprüsü (klasör seçimi, ayarlar, gözden geçirme, geçmiş) |
| `web/` | Arayüzün tamamı: `index.html`, `app.js`, `review.js`, `style.css`, `tema.css`, `tema.js` |
| `worker.py` | Arka plan işleme döngüsü (arayüzden bağımsız) |
| `extraction.py` | PDF/XML'den veri çıkarma ve doğrulama |
| `gemini.py` | Modele açılan tek kapı: hız sınırlayıcı, yeniden deneme, hata sınıflandırma |
| `sema.py` | Şema: `alanlar.json` okuma/yazma, prompt ve tablo türetimi |
| `fatura.py` | Varsayılan şemanın sabitleri (`ALANLAR`, `SUTUN`) ve türetilmiş değerler |
| `review.py` | Gözden geçirme ekranının saf mantığı |
| `duzeltme.py` | VKN bazlı öğrenen düzeltme kuralları |
| `excel_utils.py` | Excel okuma/yazma, bağlantılar, Özet sayfası |
| `ozet.py` | Özet hesaplama (aylık, firma, para birimi bazlı) |
| `hatalar.py` | Hata sınıfları |
| `tests/` | pytest test paketi (179 test) |
| `build.bat` | Windows EXE derleme betiği |

## 📜 Lisans
Bu proje MIT lisansı ile lisanslanmıştır. Özgürce kullanabilir, değiştirebilir ve dağıtabilirsiniz.
