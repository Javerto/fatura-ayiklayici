# Fatura Ayıklayıcı (Invoice Extractor)

Türkçe PDF ve XML e-faturalarından otomatik veri çıkarma uygulaması. Google Gemini AI kullanarak fatura bilgilerini okur ve düzenli bir Excel dosyasına aktarır.

## 🚀 Özellikler

- **Hibrid PDF İşleme:** Dijital PDF'lerde doğrudan metin üzerinden, taranmış (resim) PDF'lerde ise gelişmiş OCR (Vision) üzerinden veri ayıklar.
- **XML Desteği:** UBL formatındaki e-faturaları (XML) doğrudan ve hatasız ayrıştırır.
- **Yapay Zeka Gücü:** Veri çıkarma için Google'ın en yeni Gemini AI modellerini kullanır.
- **Paralel İşleme:** PDF dosyalarını 5 iş parçacığı (thread) ile hızlıca işler.
- **Akıllı Excel Çıktısı:** Kaynak dosyalara doğrudan tıklanabilir bağlantılar içeren, düzenli bir Excel tablosu oluşturur.
- **Artımlı Çalışma:** Daha önce işlenmiş faturaları algılar ve atlar, sadece yeni eklenenleri işler.
- **Modern Arayüz:** Catppuccin temalı, koyu ve açık mod desteği sunan kullanıcı dostu GUI.

## 🛠️ Kurulum

### 1. Gereksinimler
- Python 3.11 veya üzeri.
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/)'dan ücretsiz alabilirsiniz).

### 2. Bağımlılıkları Yükleme
Projeyi klonladıktan sonra terminalde şu komutu çalıştırın:
```bash
pip install -r requirements.txt
```

### 3. Yapılandırma
- Proje klasöründeki `.env.example` dosyasının adını `.env` olarak değiştirin.
- İçindeki `GEMINI_API_KEY` kısmına kendi API anahtarınızı yapıştırın.
*(Not: Uygulama ilk açılışta API key girilmemişse size otomatik olarak soracaktır).*

## 📖 Kullanım

### Geliştirme Modunda Çalıştırma
```bash
python main.py
```

### Adımlar
1. **Klasör Seç:** Faturalarınızın (PDF/XML) bulunduğu klasörü seçin.
2. **Başlat:** İşlemi başlatın. Log ekranından hangi faturanın dijital, hangisinin OCR ile okunduğunu takip edebilirsiniz.
3. **Excel'i Aç:** İşlem bittiğinde oluşan dosyayı tek tıkla açın.

### EXE Olarak Derleme (Windows)
Uygulamayı kurulum gerektirmeyen tek bir `.exe` dosyasına dönüştürmek için:
```bash
build.bat
```
Çıktı `dist/` klasörü içinde oluşacaktır.

## ⚙️ Özelleştirme

### Prompt Güncelleme
Uygulamanın faturalardan hangi alanları çıkaracağını veya nasıl davranacağını değiştirmek isterseniz `extraction.py` dosyasındaki `PROMPT_SABLON` değişkenini düzenleyebilirsiniz. 

Örneğin, sadece belirli ürün kalemlerini veya özel vergi kodlarını çekmek için promptu Türkçe olarak güncellemeniz yeterlidir.

### Model Seçimi
Varsayılan olarak `gemma-4-31b-it` kullanılmaktadır. Daha yüksek doğruluk için `extraction.py` içindeki `GEMMA_MODEL` değerini değiştirebilirsiniz.

## 📂 Proje Yapısı
- `main.py`: Uygulamanın giriş noktası.
- `gui.py`: Tkinter arayüzü ve arka plan işleme mantığı.
- `extraction.py`: AI ve XML tabanlı veri çıkarma motoru.
- `excel_utils.py`: Excel raporlama ve dosya bağlantıları.
- `build.bat`: Windows için derleme betiği.

## 📜 Lisans
Bu proje MIT lisansı ile lisanslanmıştır. Özgürce kullanabilir, değiştirebilir ve dağıtabilirsiniz.
