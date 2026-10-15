# Alan Sözlüğü

Bu dosya projenin ortak dilini tutar: bir terim burada tanımlıysa kodda, commit
mesajlarında ve tartışmalarda **aynı** anlamda kullanılır. Yeni bir kavrama isim
verirken önce buraya bak; buradaki bir terim bulanıklaşırsa burada keskinleştir.

## Alan terimleri

**Fatura satırı** — Tek bir faturadan çıkarılan alanlar kümesi (fatura no, tarih,
şirket, VKN, tutarlar, kaynak dosya yolu). Taşıyıcısı düz bir `dict`; hangi
alanları taşıdığını **Şema** söyler. Türetilen değerler (`kaynak`, `dosya_adi`)
`fatura.py`'de.

**Şema** (`sema.Sema`) — Faturadan hangi alanların çıkarılacağının tek gerçek
kaynağı. Bir veri dosyasıdır (`alanlar.json`; frozen modda AppData, değilse
proje kökü), ilk açılışta gömülü tohumdan yazılır, sonrası hep dosyadan okunur.
Model promptu, Excel sütunları/başlıkları/genişlikleri, gözden geçirme formu ve
öğrenilen alanlar ondan **türer** — prompt ile tablo ayrışamaz. Alan başına:
`anahtar` (etiketten bir kez türetilir, asla değişmez), `etiket`, `tip`
(`metin`/`tarih`/`sayi`), `sutun` (sistem atar, yeniler sona), `cekirdek`,
`aktif`, `zorunlu`, `ogrenilir`, `aciklama` (modele giden metin). Kodda bir
**değer** olarak dolaşır: fonksiyonlar `sema=None` alır, verilmezse
`sema.VARSAYILAN` (tohum). Dosyayı yalnızca `Api` okur. Arşivin kendi gömülü
şeması (`_Sema` sayfası) ayrı bir şeydir: o Excel'in hangi düzenle yazıldığını
söyler.

**Çekirdek alan** — Pasife alınamayan alan: `fatura_no`, `fatura_tarihi`,
`sirket_adi`, `vkn`, `vergiler_dahil_tutar`, `para_birimi` (`sema.CEKIRDEK`).
Özet sayfası, Excel formülleri ve gözden geçirme kartı bunların anlamına
dayanır. Kendi gömülü doğrulama kuralları vardır (VKN biçimi, 16 karakter
fatura no, örtük KDV oranı, mükerrer). Kısıt `sema.coz`'da denetlenir: çekirdeği
pasif şema reddedilir (`ValueError`). `kdv_haric_tutar` bilinçli olarak
çekirdek dışıdır.

**Pasif alan** — `aktif: false` olan alan; bir alanı "kaldırmak" budur, gerçek
silme yoktur. Prompt'a girmez, formda görünmez, yeni faturada doldurulmaz
(worker düşürür), uyarı üretmez — ama **Excel sütunu ve arşivdeki eski verisi
korunur**. Çekirdek dışı aktif alanlar yalnızca `zorunlu` bayrağı (boşsa uyarı)
ve tip dönüşüm hatasıyla denetlenir.

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
