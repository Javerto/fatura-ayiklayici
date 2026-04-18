# Fatura Ayıklayıcı

Türkçe PDF ve XML e-faturalarından otomatik veri çıkarma uygulaması. Google Gemini AI kullanarak fatura bilgilerini okur ve düzenli bir Excel dosyasına aktarır.

## Özellikler

- PDF faturalardan AI destekli veri okuma (Google Gemini)
- XML e-fatura (UBL formatı) doğrudan ayrıştırma
- Paralel PDF işleme (5 iş parçacığı)
- Çıktı: Kaynak dosyalara tıklanabilir bağlantı içeren Excel
- Daha önce işlenmiş faturaları atlama (artımlı çalışma)
- Koyu/açık tema desteği
- Kurulum gerektirmez: tek dosya EXE olarak dağıtılabilir

## Gereksinimler

- Python 3.11+
- Google Gemini API key ([aistudio.google.com](https://aistudio.google.com) adresinden ücretsiz alınabilir)

## Kurulum

```bash
pip install google-genai pymupdf python-dotenv openpyxl
```

## Kullanım

### Geliştirme modunda çalıştırma

```bash
# .env.example dosyasını kopyala ve API key'ini gir
cp .env.example .env

python main.py
```

İlk çalıştırmada uygulama otomatik olarak API key girişi isteyecektir.

### Adımlar

1. **Klasör seç** — PDF ve/veya XML faturalarının bulunduğu klasörü seç
2. **Başlat** — İşlemi başlat; uygulama yeni faturaları otomatik algılar
3. **Excel'i Aç** — Oluşturulan Excel dosyasını aç

## EXE Derleme (Windows)

```bash
build.bat
```

Çıktı: `dist/FaturaAyiklayici.exe` (~41 MB, bağımlılık gerektirmez)

> EXE modunda `.env` ve `gecmis.json` dosyaları `%APPDATA%\FaturaAyiklayici` klasörüne yazılır.

## Yapılandırma

`.env` dosyası (proje kök dizini veya EXE modunda AppData):

```
GEMINI_API_KEY=your_key_here
TEMA=dark   # dark veya light
```

## Proje Yapısı

```
main.py          — Giriş noktası
gui.py           — Tkinter arayüzü ve arka plan işleme
extraction.py    — PDF/XML veri çıkarma ve doğrulama
excel_utils.py   — Excel okuma/yazma
build.bat        — EXE derleme scripti
```

## Teknik Detaylar

| Ayar | Değer |
|------|-------|
| AI Modeli | `gemma-4-31b-it` (Google Gemini) |
| Paralel iş parçacığı | 5 |
| API istek limiti | 14 istek/dakika |
| Zaman aşımı | 180 saniye |
| Yeniden deneme | Maksimum 5 |

## Ekran Görüntüsü

> Uygulama Catppuccin Mocha (koyu) ve Catppuccin Latte (açık) tema desteği sunar.

## Lisans

MIT
