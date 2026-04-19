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
- **Dağıtım:** PyInstaller (Windows EXE)

## Mimari Yapı

Proje dört ana modülden oluşmaktadır:

1.  **`main.py`**: Uygulamanın giriş noktası. Tkinter kök penceresini oluşturur ve `App` sınıfını başlatır.
2.  **`gui.py`**: 
    - Kullanıcı arayüzünü (UI) yönetir.
    - Uzun süren işlemleri ana thread'i dondurmamak için ayrı bir `worker` thread'inde çalıştırır.
    - Thread'ler arası iletişim için `queue.Queue` ve `threading.Event` (durdurma için) kullanır.
    - Tema yönetimi ve işlem geçmişi (gecmis.json) burada tutulur.
3.  **`extraction.py`**: 
    - **XML:** UBL e-fatura standartlarına göre doğrudan ElementTree ile ayrıştırma yapar.
    - **PDF:** Sayfaları görsele çevirir ve Gemini API'ye gönderir. 
    - **Rate Limiting:** Dakikada 14 istek (RPM) sınırını aşmamak için `_rpm_bekle` mekanizması içerir.
    - **Doğrulama:** `veri_dogrula` fonksiyonu ile ayıklanan verilerin mantıksal kontrolünü yapar.
4.  **`excel_utils.py`**: Excel dosyasını oluşturur, verileri yazar ve her satıra ilgili dosyanın yerel bağlantısını (link) ekler.

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
