# Kodlama standartları

İnceleme (review) sırasında okunur. Burada yalnızca muhakeme isteyen kurallar var; mekanik olanlar `tests/test_kurallar.py` ve CI'daki `ruff check --select F` ile zaten denetleniyor. Arka plan: `CLAUDE.md` (veri güvenliği), `docs/mimari.md`, `docs/arayuz.md`.

Her bulguda kuralın adını ve diff'teki satırı göster.

## Python

- **Tek kapı.** Model çağrısı yalnızca `gemini.py`'den, eLogo API'si yalnızca `elogo.py`'den geçer. Başka bir modülde `google.genai` ya da eLogo URL'si görürsen bulgu.
- **JS güven sınırı.** `Api`'nin her public metodu, JS'ten gelen argümanı Python tarafında doğrular (indeks aralığı, çalışma kilidi). Arayüzde buton kapatmak yetmez.
- **`Api` iç durumu `_` önekli.** Yeni public nitelik, pywebview'in proxy taramasına girer.
- **Veri kaybına karşı hata.** Okunamayan dosya hata fırlatır, boş sonuç döndürmez. Excel/JSON yazımı `.tmp` + `os.replace` ile olur. `excel_olustur` gibi yazma yolları her `OSError`'ı `ExcelHatasi`'na sarar.
- **Şema geçirilir.** Kullanıcının alanlarına uyması gereken kod `sema` parametresini alır; `fatura.ALANLAR`/`SUTUN` sabitleri yalnızca eski arşivleri okumak içindir.
- **Zaman ve dış bağımlılık enjekte edilir.** Bekleme, saat ve model istemcisi parametre olarak gelir ki test gerçek saati ve ağı beklemesin.
- **Olay sözleşmesi.** `log_q`'ya giden olayın anahtarları değişirse `web/` tarafı ve `tests/test_olay_sozlesmesi.py` aynı diff'te güncellenir.

## Arayüz (`web/`)

- **`await` sonrası seçimi tekrar kontrol et.** `review.js`'te her `await`'ten sonra DOM'a dokunmadan önce `R.secili` hâlâ aynı satır mı bakılır.
- **Düzenleme sırasında formu yeniden kurma.** `innerHTML` ile yeniden çizim Tab'dan sonra yazılan karakteri yer ve odağı düşürür; değer ve uyarı yerinde güncellenir.
- **Boyut bağlama yazılır.** `.actions .btn-primary{flex:1}` gibi; bileşenin kendisine yazılan boyut onu başka bağlamda (modal) bozar.
- **Türkçe metin kaynakta doğru yazılır.** Başlık harfi CSS `text-transform` ile değil, metnin kendisinde (`İşleniyor`).

## Testler

- **Koruma testi kırmızıya dönerken görülmüş olmalı.** Hata geri konur, test kırmızı olur, sonra kaldırılır. PR açıklamasında ya da commit'te bunun yapıldığı görülmüyorsa sor.
- **Yama, adın kullanıldığı yere yapılır** (`worker.pdf_text_ayikla`), tanımlandığı yere değil.
