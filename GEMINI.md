# Fatura Ayıklayıcı - Geliştirici Kılavuzu

Bu dosya, Gemini CLI ve geliştiriciler için projenin yapısını, çalışma prensiplerini ve geliştirme standartlarını özetler.

## Proje Genel Bakışı

**Fatura Ayıklayıcı**, PDF ve XML (UBL) formatındaki e-faturalardan veri ayıklayan ve bu verileri Excel formatında raporlayan bir Python uygulamasıdır. Veri çıkarma işlemi için Google Gemini AI (`gemma-4-31b-it`) modelini kullanır.

### Ana Teknolojiler
- **Dil:** Python 3.11+
- **AI:** Google Gemini AI (google-genai SDK)
- **Arayüz:** Tkinter (Özel Catppuccin temalı)
- **PDF İşleme:** PyMuPDF (fitz)
- **Excel:** openpyxl
- **Arayüz:** pywebview (Windows WebView2) + HTML/CSS/JS
- **Dağıtım:** PyInstaller (Windows EXE)

## Mimari Yapı

Proje şu ana modüllerden oluşur:

1.  **`main.py`**: Giriş noktası. Kayıtlı boyutla pywebview penceresini açar.
2.  **`api.py`**: Arayüz ile Python arasındaki köprü.
    - Genel metotları arayüze `pywebview.api.<metot>()` olarak açılır.
    - Uzun süren işi ayrı bir `worker` thread'inde çalıştırır; iletişim `queue.Queue` ve
      `threading.Event` ile olur, olaylar gruplanıp arayüze iletilir.
    - Ayarlar (.env), işlem geçmişi (gecmis.json) ve gözden geçirme akışı burada yönetilir.
    - **Dikkat:** iç durum `_` önekiyle saklanmalıdır; pywebview genel niteliklere özyineleyerek
      girer ve pencere referansı açıkta kalırsa uygulama açılışta donar.
3.  **`web/`**: Arayüzün tamamı (HTML/CSS/JS). Altı tema `tema.css` içinde.
4.  **`extraction.py`**: 
    - **XML:** UBL e-fatura standartlarına göre doğrudan ElementTree ile ayrıştırma yapar.
    - **PDF:** Sayfaları görsele çevirir ve Gemini API'ye gönderir. 
    - **Rate Limiting:** Dakikada 14 istek (RPM) sınırını aşmamak için `_rpm_bekle` mekanizması içerir.
    - **Doğrulama:** `veri_dogrula` fonksiyonu ile ayıklanan verilerin mantıksal kontrolünü yapar.
5.  **`excel_utils.py`**: Excel dosyasını oluşturur, verileri yazar ve her satıra ilgili dosyanın yerel bağlantısını (link) ekler.

## Kurulum ve Çalıştırma

### Bağımlılıkları Yükleme
```bash
pip install -r requirements.txt
```

### Uygulamayı Başlatma
```bash
python main.py
```

### EXE Derleme
Windows üzerinde bağımsız bir EXE oluşturmak için:
```bash
build.bat
```

## Geliştirme Konvansiyonları

### Hata Yönetimi
- Proje özel hata sınıfları kullanır (`APIKeyHatasi`, `InternetHatasi`, `PDFHatasi` vb.).
- Kritik hatalarda işlem durdurulur, ancak tekil fatura hatalarında (bozuk PDF vb.) fatura atlanır ve log tutulur.

### Paralel İşleme
- PDF'ler `concurrent.futures.ThreadPoolExecutor` ile varsayılan olarak 5 paralel iş parçacığında işlenir.
- API limitlerine (`RPM_LIMIT`) dikkat edilmelidir.

### Yapılandırma
- Hassas bilgiler ve kullanıcı tercihleri `.env` dosyasında saklanır.
- EXE modunda `.env` ve `gecmis.json` dosyaları `%APPDATA%\FaturaAyiklayici` dizinine taşınır.

## Önemli Notlar
- **Veri Güvenliği:** API Key'ler asla koda gömülmemeli, her zaman `.env` üzerinden yönetilmelidir.
- **Doğruluk:** AI tabanlı çıkarma her zaman %100 doğru olmayabilir. Bu nedenle `veri_dogrula` uyarıları kullanıcı arayüzünde gösterilir.
- **Bağlantılar:** Excel'deki dosya yolları mutlak (absolute) yoldur, bu sayede Excel dosyası taşınsa bile bağlantılar yerel bilgisayarda çalışmaya devam eder.
