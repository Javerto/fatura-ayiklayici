# Spec: Alan şemasının koddan çıkarılması

## Problem Statement

Uygulamanın adı "fatura ayıklayıcı" ama pratikte "şu 11 alanı ayıklayıcı".
Hangi bilgilerin faturadan çıkarılacağı bugün üç ayrı Python literal'inde gömülü:
model promptu, alan tablosu (Excel sütunu / form etiketi / tip) ve doğrulama
kuralları.

Sonuç: kullanıcı kendi işine yaramayan bir alanı (`sira_no` yalnızca yatırım
teşvik dosyası tutanlar için anlamlı) atamıyor, ihtiyaç duyduğu bir alanı
(sipariş no, irsaliye no, ödeme vadesi, GTİP) ekleyemiyor. Tek çözüm kaynak
kodu düzenleyip EXE'yi yeniden derlemek — yani uygulamayı kullanan kişi için
çözüm yok.

Uygulamanın ana amacı "promptla istenen bilgileri faturadan ayıklamak" ise,
prompt kullanıcının olmalı; bugün kodun.

## Solution

Alan seti bir veri dosyası olur (`alanlar.json`); model promptu, Excel
sütunları, gözden geçirme formu ve öğrenen düzeltme alanları ondan **türer**.
EXE kullanıcısı alanlarını uygulama içindeki bir editör ekranından tanımlar:
etiket, tip, ve modele verilecek açıklama.

Değişikliğin doğru olup olmadığını görmek için editörde bir **"Dene"** butonu
vardır: seçilen tek bir faturayı mevcut şemayla işler, sonucu gösterir, Excel'e
hiçbir şey yazmaz.

Arşiv güvenliği tasarımın merkezindedir: kullanıcı şemayı bozarak aylarca
birikmiş Excel'i yok edememelidir.

## User Stories

1. Bir muhasebe kullanıcısı olarak, faturalarımdan "sipariş no" bilgisini de çıkarmak istiyorum ki Excel'de sipariş eşleştirmesini elle yapmayayım.
2. Bir muhasebe kullanıcısı olarak, işime yaramayan `sira_no` alanını kaldırmak istiyorum ki Excel'im gereksiz boş sütunla dolmasın.
3. Bir muhasebe kullanıcısı olarak, alan eklemek için geliştiriciye ihtiyaç duymamak istiyorum ki kendi ihtiyacımı kendim karşılayayım.
4. Bir şema düzenleyen kullanıcı olarak, "Şirket Adı" etiketini "Satıcı Firma" yapmak istiyorum ki Excel benim kurumumda kullanılan terimlerle konuşsun.
5. Bir şema düzenleyen kullanıcı olarak, bir alanın modele verilen açıklamasını değiştirmek istiyorum ki kendi fatura tipimde daha doğru okunsun.
6. Bir şema düzenleyen kullanıcı olarak, alanların gözden geçirme formundaki sırasını değiştirmek istiyorum ki en çok düzelttiğim alan en üstte olsun.
7. Bir şema düzenleyen kullanıcı olarak, bir alanı "firma için hatırla" kapsamına almak istiyorum ki aynı firmanın sonraki faturalarında elle düzeltmeyeyim.
8. Bir şema düzenleyen kullanıcı olarak, yeni alanın tipini (metin/tarih/sayı) seçmek istiyorum ki Excel'de toplanabilsin ve doğru biçimlensin.
9. Bir şema düzenleyen kullanıcı olarak, yeni bir alan tanımladığımda Excel sütun numarasıyla hiç uğraşmak istemiyorum ki yanlış yere yazıp arşivi bozmayayım.
10. Bir şema düzenleyen kullanıcı olarak, alanın iç kimliğini (`anahtar`) hiç görmek istemiyorum ki tasarımın teknik detayı beni ilgilendirmesin.
11. Bir şema düzenleyen kullanıcı olarak, boş etiketli ya da aynı adı taşıyan iki alan kaydedememek istiyorum ki farkında olmadan bozuk bir şema üretmeyeyim.
12. Bir şema düzenleyen kullanıcı olarak, açıklamasını boş bıraktığımda uyarılmak ama engellenmemek istiyorum ki kararı ben vereyim.
13. Bir şema düzenleyen kullanıcı olarak, değişikliklerimin ancak "Kaydet" dediğimde yürürlüğe girmesini istiyorum ki yarım yazdığım bir alan modele gitmesin.
14. Bir şema düzenleyen kullanıcı olarak, kaldırdığım alanın eski faturalardaki verisinin Excel'de kalmasını istiyorum ki geçmişimi kaybetmeyeyim.
15. Bir şema düzenleyen kullanıcı olarak, faturanın olmazsa olmaz alanlarını (fatura no, tarih, firma, VKN, tutar, para birimi) yanlışlıkla silememek istiyorum ki uygulamanın temel işlevini bozmayayım.
16. Bir şema düzenleyen kullanıcı olarak, bir alanın tipini veri yazıldıktan sonra değiştirememek istiyorum ki Excel sütunumda metin ve sayı karışıp toplamlar sessizce yanlış çıkmasın.
17. Bir şema düzenleyen kullanıcı olarak, yazdığım açıklamanın işe yarayıp yaramadığını tek bir fatura üzerinde denemek istiyorum ki 200 faturalık kotayı harcadıktan sonra öğrenmeyeyim.
18. Bir şema düzenleyen kullanıcı olarak, deneme yaptığımda Excel'e hiçbir şey yazılmamasını istiyorum ki denemek risksiz olsun.
19. Bir muhasebe kullanıcısı olarak, fatura işlenirken şema editörünün kilitli olmasını istiyorum ki aynı Excel'de yarı-yarıya çıktı oluşmasın.
20. Bir arşiv sahibi olarak, şemamı değiştirdikten sonra eski bir klasörü tekrar işlediğimde uyarılmak istiyorum ki o Excel'in farklı bir alan setiyle oluşturulduğunu bileyim.
21. Bir arşiv sahibi olarak, şema değişse bile eski Excel dosyalarımın doğru okunmasını istiyorum ki sütunlar kaymasın.
22. Bir arşiv sahibi olarak, uygulamanın önceki sürümleriyle üretilmiş Excel'lerimin okunmaya devam etmesini istiyorum ki güncelleme beni geçmişimden etmesin.
23. Bir muhasebe kullanıcısı olarak, eklediğim alanların gözden geçirme ekranında da düzenlenebilir olmasını istiyorum ki modelin hatasını onay öncesi düzeltebileyim.
24. Bir muhasebe kullanıcısı olarak, zorunlu işaretlediğim bir alan boş geldiğinde uyarı görmek istiyorum ki eksik faturayı fark edeyim.
25. Bir muhasebe kullanıcısı olarak, Özet sayfasının eklediğim alanlardan etkilenmemesini istiyorum ki anlamsız toplamlar görmeyeyim.
26. Bir geliştirici olarak, şema dosyasının bir sürüm numarası taşımasını istiyorum ki biçim ileride değişirse eski dosyayı tanıyabileyim.
27. Bir geliştirici olarak, şema dosyası ilk açılışta kendiliğinden oluşsun istiyorum ki "dosya yok" hâli kalıcı bir ikinci kod yolu olmasın.
28. Bir geliştirici olarak, altın küme ölçümünün şemadan türemeye devam etmesini istiyorum ki doğruluk ölçüsünü kaybetmeyeyim.
29. Bir geliştirici olarak, prompt ile alan tablosunun asla ayrışamamasını istiyorum ki "prompt'ta var, tabloda yok" sınıfı sessiz veri kaybı imkânsız olsun.

## Implementation Decisions

### Yeni modül: şema

- Şemanın **tek kapısı** yeni bir modül olur. Sorumlulukları: dosyadan okuma,
  atomik yazma, doğrulama, ve türetilmiş görünümleri üretme (prompt metni,
  Excel sütun bilgisi, form alanları, öğrenilen alanlar, tip haritası).
- `fatura.ALANLAR` bu modülün ürettiği değere dönüşür. `SUTUN`,
  `DUZENLENEBILIR_ALANLAR`, `OGRENILEN_ALANLAR` türetilmeye devam eder —
  tüketicilerin (excel_utils, review, duzeltme, altin) kodu değişmez.
- Dosya okuma/yazma imzası `duzeltme.kurallari_oku/kurallari_yaz(yol, ...)`
  desenini birebir izler; yazma atomiktir (geçici dosya + `os.replace`),
  çünkü bozuk bir şema dosyası kullanıcının tüm alan tanımlarını yok eder.

### Şema biçimi

```json
{ "surum": 1,
  "alanlar": [
    { "anahtar": "fatura_no", "etiket": "Fatura No", "tip": "metin",
      "sutun": 2, "cekirdek": true, "aktif": true, "zorunlu": true,
      "ogrenilir": false, "aciklama": "<modele giden alan açıklaması>" }
  ] }
```

- `anahtar`: etiketten türetilir, bir kez üretilir, **asla değişmez**.
  Kullanıcı görmez. Slug çakışmasında sona sayı eklenir.
- `sutun`: sistem atar, kullanıcı görmez/seçmez. Yeni alanlar **sona** eklenir;
  mevcut sütunlar asla yeniden numaralandırılmaz.
- `cekirdek`: silinemeyen/pasife alınamayan alan. Çekirdek küme:
  `fatura_no`, `fatura_tarihi`, `sirket_adi`, `vkn`, `vergiler_dahil_tutar`,
  `para_birimi`.
- `aktif`: `false` = pasif. Prompt'a girmez, formda görünmez, yeni faturalarda
  doldurulmaz; Excel sütunu ve arşivden okuma **korunur**.
- `tip`: `metin` | `tarih` | `sayi`. Yalnızca alan oluşturulurken seçilir,
  sonrasında kilitlidir.

### Dikiş

- Tek yeni dikiş: **`Sema` bir değerdir**, ilgili fonksiyonlara varsayılanlı
  parametreyle geçirilir (`sema=None` → süreç ömürlü aktif şema). Prior art:
  `worker(..., istemci=None)`, `Sinirlayici`'nin süreç ömürlü varsayılanı,
  `Api(kok=...)`.
- Şema dosyasının konumu `Api(kok=...)`'tan çözülür; testler gerçek
  `alanlar.json`'a dokunmaz.

### Prompt türetimi

- Prompt'un sabit Türkçe yönerge başlığı kodda kalır; JSON iskeleti aktif
  alanlardan üretilir (alan başına `"anahtar": "aciklama"`).
- Serbest prompt metni **yoktur**. Prompt ile tablo yapısal olarak ayrışamaz.

### Arşiv ↔ şema bağı

- Excel'e gizli bir şema sayfası yazılır (`anahtar → sütun`).
- Okuma üç kademelidir: gömülü şema → başlık eşlemesi → bugünkü sabit sütun
  numaraları. Eski Excel dosyaları bu sayede okunmaya devam eder.
- Arşivin gömülü şeması aktif şemadan farklıysa gözden geçirme ekranında
  **koşu düzeyinde bir uyarı** gösterilir (satır düzeyinde değil — bugünkü
  `(alan, mesaj)` sözleşmesinin dışında, `kesildi` bayrağının durduğu yerde).
  İşlem durdurulmaz.

### Doğrulama

- Çekirdek alanların mevcut gömülü kuralları (VKN biçimi, örtük KDV oranı,
  16 karakter fatura no, mükerrer kontrolü) aynen korunur.
- Kullanıcı alanları için yalnızca: `zorunlu` bayrağı (boşsa uyarı) ve tip
  dönüşüm hatası uyarısı. Regex/aralık tanımı yoktur.
- Şema doğrulaması (editörde): boş etiket ve yinelenen etiket kaydetmeyi
  engeller; boş açıklama yalnızca uyarır.

### Editör arayüzü

- Gözden geçirme ekranıyla aynı desen: ayrı tam ekran, gizli `div`, tek pencere.
- Düzenlenebilir: etiket, açıklama, sıra, `ogrenilir`, (yalnızca oluştururken) tip.
- Çekirdek alanlar **görünür**; etiketi/açıklaması/sırası değişir, silinemez,
  tipi değişmez.
- Açık **Kaydet** butonu. Gözden geçirme formundaki "alandan çıkınca uygula"
  deseni burada geçerli değildir.
- Bir koşu sürerken editör kilitlidir (`basla()` guard'ının kardeşi).
- Form grubu düzenlenemez; kullanıcı alanları mevcut "Diğer" grubuna düşer.

### "Dene" akışı

- Editörden seçilen tek bir fatura, aktif şemayla işlenir; tek model çağrısı.
- Sonuç ekranda gösterilir, **Excel'e yazılmaz**, geçmişe kaydedilmez.
- Mevcut altyapı kullanılır: worker tek dosyalık koşuyu zaten destekliyor,
  gözden geçirme ekranının metin izdüşümü sonucu göstermeye hazır.

### Göç

- Şema dosyası ilk açılışta gömülü tohumdan yazılır; sonrası hep dosyadan
  okunur. Gömülü tohum bugünkü alan tablosunun aynısıdır.
- Frozen modda AppData, değilse proje kökü (`duzeltmeler.json` deseni).

### Kaldırılan kısıt

- "Excel sütun numaraları açıkça yazılır, listedeki sıradan türetilmez" kuralı
  gömülü şema + başlık eşlemesi geldikten sonra gereksizleşir.

## Testing Decisions

İyi test, dışarıdan gözlenen davranışı sınar: bir fonksiyonun iç adımlarını
değil, girdiye karşılık ürettiği çıktıyı ve dosyaya yazdığını. Bu projede
kurulu ölçüt: arayüzsüz, ağsız, gerçek yapılandırma dosyalarına dokunmayan.

- **Şema modülü** — okuma/yazma gidiş-dönüşü, bozuk/eksik dosyada davranış,
  atomik yazma, sürüm alanı, slug türetimi ve çakışması, doğrulama kuralları
  (boş/yinelenen etiket). Prior art: `tests/test_duzeltme.py`.
- **Prompt türetimi** — saf fonksiyon: aktif alanlar prompt'a girer, pasifler
  girmez, açıklama metni aktarılır. Prior art: `tests/test_fatura.py`.
- **Excel gidiş-dönüşü** — yaz → oku; gömülü şema sayfasıyla, gömülü şemasız
  (başlık eşlemesi), ve ikisi de olmayan eski dosya (sabit sütun) için ayrı
  ayrı. Pasif alanın sütununun ve verisinin **korunduğu** senaryo bu grubun en
  kritik testidir. Prior art: `tests/test_excel_url.py`,
  `tests/test_excel_kaynak.py`, `tests/test_excel_guvenlik.py`.
- **Uçtan uca worker** — sahte `istemci` + test `Sema`'sı ile: özel alan
  çıkarılıyor, pasif alan çıkarılmıyor. Prior art: `tests/test_worker.py`.
- **Api uç noktaları** — `Api(kok=tmp_path)` ile şema okuma/kaydetme/deneme;
  koşu sürerken kaydetmenin reddi; geçersiz girdilerin reddi (JS bir güven
  sınırıdır). Prior art: `tests/test_api.py`, `tests/test_review_onayla.py`.
- **Olay sözleşmesi** — editör ve uyuşmazlık uyarısı için Python↔JS anahtarları.
  Prior art: `tests/test_olay_sozlesmesi.py`.
- **Api'nin genel nitelik kuralı** — yeni public metotlar pywebview'in proxy
  taramasını bozmamalı; mevcut guard test bunu zaten kapsıyor.

Doğruluk ölçümü teste ait değildir: prompt türetimi devreye girdiğinde
`altin.py` **önce/sonra** koşulur. Bu adım atlanırsa doğruluk kaybı sessiz olur.

## Out of Scope

- Adlandırılmış şema profilleri (birden fazla alan seti arasında geçiş).
- Alanlara rol etiketi verip Özet/formülleri role bağlama.
- Kullanıcı tanımlı regex veya sayı aralığı doğrulaması.
- Gözden geçirme formundaki grupların düzenlenebilmesi.
- Alanın gerçekten silinmesi (arşivdeki sütunun kaldırılması).
- Kullanıcı alanlarının Özet sayfasına girmesi.
- Altın küme yeteneğinin ürün içine taşınması.
- Faturaların alt klasörlerden taranması, VKN kontrol hanesi, tarih akla
  yatkınlık kontrolü — ayrı işler.

## Further Notes

**Tek ciddi risk: prompt türetimi doğruluğu düşürebilir.** Bugünkü prompt
elle ayarlanmış Türkçe prose; şemadan üretilen metin kelime kelime aynı
olmayacak. Altın küme ölçümü bu aşamada zorunludur, gerekirse üretim biçimi
ölçüme göre ayarlanır.

**Uygulama sırası** (her adım bir commit, her adımda doğrulama):

1. Arşiv okumayı sütun numarasından kopar → eski Excel aynen okunuyor, yeni
   dosyada gömülü şema var, üç kademe için test.
2. Şema dosyası okuma yolu (tohum → dosya, arayüz yok) → mevcut testler
   değişmeden geçer, dosya silinince yeniden doğar.
3. Prompt türetimi → **altın küme önce/sonra koşusu.**
4. Pasif alan + çekirdek kısıtı (saf mantık) → pasif alanın sütununu koruduğu test.
5. Editör ekranı → uygulama açılıp kullanıcıya gösterilir (arayüz hataları
   pytest'te görünmüyor).
6. Dene butonu → tek çağrı, Excel'e dokunmuyor.
7. Şema/arşiv uyuşmazlık uyarısı → eski şemayla yazılmış Excel'de uyarı çıkıyor.

**`kdv_haric_tutar` çekirdek dışıdır** ve pasife alınabilir. Pasife alınırsa
`vergi_tutari` formülü (`=dahil−hariç`) ve örtük KDV oran kontrolü anlamsızlaşır;
ikisi de "alan yoksa atla" ile ele alınır. Bilinçli karardır.

**Şema global, arşivler klasör başınadır.** Bu ayrışma tasarımda kabul edilmiş,
gömülü şema sayesinde tespit edilebilir kılınmış ve uyarıyla ele alınmıştır —
engellenmemiştir.
