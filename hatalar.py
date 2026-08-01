"""Uygulamanın özel istisnaları.

Ayrı bir modülde duruyorlar çünkü bir istisnayı *fırlatan* modül ile onu
*yakalayan* modül genelde farklı: `ExcelHatasi`'nı `excel_utils` fırlatır,
`worker` ve `api` yakalar. Taksonomi tek bir modülde olmazsa yakalayan taraf,
sırf istisna için fırlatanı (ya da üçüncü bir modülü) import etmek zorunda
kalır — `excel_utils`'in `ExcelHatasi`'nı `extraction`'dan alması böyle
olmuştu.

Sınıflandırma, hatanın işlemi ne kadar durdurduğuna göre:
  - APIKeyHatasi  → tüm iş durur
  - InternetHatasi/PDFHatasi/XMLHatasi/ModelHatasi → o dosya atlanır
  - ExcelHatasi   → kayıt başarısız, düzenlemeler korunur
"""


class APIKeyHatasi(Exception):
    """API key geçersiz veya süresi dolmuş — tüm işlem durur."""


class InternetHatasi(Exception):
    """Bağlantı veya limit hatası — bu fatura atlanır."""


class PDFHatasi(Exception):
    """PDF açılamadı — bu fatura atlanır."""


class XMLHatasi(Exception):
    """XML formatı geçersiz — bu fatura atlanır."""


class ModelHatasi(Exception):
    """AI modelinden geçersiz veya ayrıştırılamayan yanıt — bu fatura atlanır."""


class ExcelHatasi(Exception):
    """Excel kaydedilemedi."""
