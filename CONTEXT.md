# Alan Sözlüğü

Bu dosya projenin ortak dilini tutar: bir terim burada tanımlıysa kodda, commit
mesajlarında ve tartışmalarda **aynı** anlamda kullanılır. Yeni bir kavrama isim
verirken önce buraya bak; buradaki bir terim bulanıklaşırsa burada keskinleştir.

## Alan terimleri

**Fatura satırı** — Tek bir faturadan çıkarılan alanlar kümesi (fatura no, tarih,
şirket, VKN, tutarlar, kaynak dosya yolu). Taşıyıcısı düz bir `dict`; sekiz
modül aynı anahtarları paylaşır. Satırdan *türetilen* değerler (`kaynak`,
`dosya_adi`) `fatura.py`'de toplandı — alan meta tablosu bilinçli olarak
ertelendi (bkz. `docs/aday-02-devir.md`).

**Kaynak** — Bir fatura satırının verisinin nereden geldiği: `Dijital` (PDF'in
gömülü metin katmanı), `OCR` (PDF görsele çevrilip modele gönderildi) veya `XML`
(UBL e-fatura doğrudan ayrıştırıldı). Satırda `_teknik_bilgi` alanında durur,
`fatura.kaynak(satir)` ile okunur (yoksa dosya uzantısından türetilir).

**Uyarı** — `(alan, mesaj)` çifti. Veriyi reddetmez, kullanıcıya gösterilir.
Alan adı, gözden geçirme ekranının uyarıyı hangi girdinin altında göstereceğini
söyler.

**Gözden geçirme** — Çıkarım bittikten sonra, Excel'e yazmadan önce kullanıcının
satırları düzelttiği/hariç tuttuğu adım. **Onaydan önce Excel'e hiçbir şey
yazılmaz.**

**Öğrenen düzeltme kuralı** — VKN bazlı, firma-sabit alanlar için kaydedilen
düzeltme (`sirket_adi`, `vergi_dairesi`). Sonraki faturalarda otomatik uygulanır.

**Arşiv** — Çıktı Excel dosyası. Yalnızca rapor değil, "neyin işlendiği"nin tek
kaydıdır; bu yüzden veri güvenliği kuralları (atomik kayıt, okunamayanda durma)
ona aittir.

## Mimari terimler

Mimari tartışmalarda `/codebase-design` sözlüğü kullanılır. Bu projede sık
geçenler:

**Dikiş (seam)** — Bir bağımlılığın testte başkasıyla değiştirilebildiği nokta.
Örnek: `ModelIstemcisi`, üretimde Gemini'ye gider, testte sahte yanıt döndürür.

**Adaptör** — Dış bir dünyayı (Gemini API'si, openpyxl, pywebview) projenin
arayüzüne çeviren modül. Sardığı şeyin adını taşır: `gemini.py`.

**Derinlik** — Bir modülün arayüzünün, sakladığı karmaşıklığa oranla darlığı.
Sığ modül: arayüzü neredeyse gerçekleştirimi kadar karmaşık olan modül.

**Silme testi** — "Bu modülü silsek karmaşıklık *toplanır mı*, yoksa sadece
*yer mi değiştirir*?" Toplanıyorsa modül hak edilmiştir.

## Modül terimleri

**Model istemcisi** (`gemini.ModelIstemcisi`) — Yapay zeka modeline yapılan
çağrının tek kapısı. Arayüzü dar: `metin_uret(parcalar) -> str`. Ardında hız
sınırlama, yeniden deneme ve hata sınıflandırma durur; çağıran bunların hiçbirini
bilmez. "Model" burada **yapay zeka modeli** demektir — alan modeli değil.

**Sınırlayıcı** (`gemini.Sinirlayici`) — Dakikadaki istek sayısını Gemini
ücretsiz kotasının altında tutar. Durumu **süreç ömürlüdür**, çalışma ömürlü
değil: kota API anahtarına aittir, kullanıcı durdurup yeniden başlattığında
sıfırlanmaz.

**Worker** — Arka plan işleme döngüsü. Arayüzden bağımsızdır; dış dünyayla
yalnızca `log_q` kuyruğu ve `stop_event` üzerinden konuşur.

## Doğrulanmış olgular

- `gemma-4-31b-it` — 2026-08-01'de `models.list()` ve gerçek bir üretim
  çağrısıyla doğrulandı: model adı geçerli ve yanıt üretiyor.
- Gemini'nin geçersiz anahtar yanıtı: `400 INVALID_ARGUMENT`,
  `'message': 'API key not valid. Please pass a valid API key.'`,
  `'reason': 'API_KEY_INVALID'`. Hata sınıflandırması bu metne dayanır.
