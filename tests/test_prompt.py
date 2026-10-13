"""Model promptu şemadan türer: prompt ile alan tablosu yapısal olarak ayrışamaz."""
import sema
from extraction import pdf_den_veri_cek

# Şemadan türetmeden önceki elle yazılmış prompt — bağımsız doğruluk kaynağı.
# Varsayılan şemanın promptu bundan yalnızca alan SIRASINDA ayrışabilir
# (prompt artık form sırasını izliyor); her satır kelimesi kelimesine aynı kalmalı.
ESKI_PROMPT = """Fatura verilerini (görsel veya metin) dikkatlice incele. Aşağıdaki alanları çıkar.
SADECE geçerli JSON döndür, başka hiçbir şey yazma, kod bloğu kullanma.

{
  "fatura_no": "fatura numarası — Türk e-fatura standardı: 3 karakter (büyük harf veya rakam) + 4 haneli yıl + 9 haneli sıra, toplam 16 karakter (örn: GIB2024000000001). Fazladan sıfır EKLEME.",
  "fatura_tarihi": "GG.AA.YYYY formatında tarih",
  "sirket_adi": "faturayı kesen SATICI şirketin adı. Faturada iki şirket varsa ALICI değil SATICI olanı yaz.",
  "tanim": "ilk kalem ya da ana hizmetin açıklaması",
  "toplam_miktar": toplam adet/miktar (sadece sayı, örnek: 7 veya 14.5),
  "kdv_haric_tutar": KDV hariç Mal/Hizmet Toplam Tutarı, TL cinsinden sayı. EUR ve TL varsa TL ver. Yoksa null,
  "vergiler_dahil_tutar": Vergiler Dahil Toplam Tutar, TL cinsinden sayı. "Ödenecek Tutar(TL)" veya "Vergiler Dahil Toplam Tutar(TL)" satırını bul. EUR/TL karışıksa TL ver,
  "para_birimi": "TL ya da yalnızca döviz varsa EUR veya USD",
  "vkn": "SATICI şirketin VKN'i (10-11 haneli). Faturada birden fazla VKN varsa SATICI olana ait olanı yaz.",
  "vergi_dairesi": "satıcı şirketin vergi dairesi adı",
  "sira_no": yatırım teşvik belgesinin kaçıncı sıra nosu — SADECE şu kalıplardan birinde geçiyorsa al: "X sırasında KDV istisnası", "Yerli Liste X sırasında", "Sıra No: X kapsamında","Liste Y-x sıra numarasına istinaden". Diğer no alanlarını ASLA alma. Yoksa null
}"""


def _satirlar(metin):
    return sorted(s.rstrip(",") for s in metin.splitlines())


def _sema(ekle=(), degistir=None):
    ham = sema.VARSAYILAN.json()
    for a in ham["alanlar"]:
        a.update((degistir or {}).get(a["anahtar"], {}))
    ham["alanlar"] += list(ekle)
    return sema.coz(ham)


def test_varsayilan_sema_promptu_eski_promptla_ayni_satirlari_tasir():
    uretilen = sema.VARSAYILAN.prompt()
    assert _satirlar(uretilen) == _satirlar(ESKI_PROMPT)
    # Geçerli JSON iskeleti: son alan virgülsüz, sonrası kapanış.
    assert uretilen.endswith('Yoksa null\n}')


def test_pasif_alan_prompta_girmez():
    s = _sema(degistir={"sira_no": {"aktif": False}})
    assert '"sira_no"' not in s.prompt()
    assert '"tanim"' in s.prompt()


def test_eklenen_alanin_aciklamasi_prompta_aktarilir():
    s = _sema(ekle=[{"etiket": "Sipariş No", "tip": "metin",
                     "aciklama": "alıcının sipariş numarası"},
                    {"etiket": "Vade", "tip": "tarih", "aciklama": ""}])
    p = s.prompt()
    assert '"siparis_no": "alıcının sipariş numarası"' in p
    assert '"vade": "Vade"' in p        # açıklama boşsa etiket


class _Istemci:
    def __init__(self, yanit):
        self.yanit, self.parcalar = yanit, None

    def metin_uret(self, parcalar):
        self.parcalar = parcalar
        return self.yanit


def test_pdf_cikarimi_verilen_semanin_promptunu_gonderir_ve_alanlari_tipler():
    s = _sema(ekle=[{"etiket": "Koli Sayısı", "tip": "sayi", "aciklama": "koli"},
                    {"etiket": "Vade", "tip": "tarih", "aciklama": "vade"}])
    ist = _Istemci('{"fatura_no": "GIB2024000000001", "koli_sayisi": "1.234,5",'
                   ' "vade": "05.03.2024"}')

    veri = pdf_den_veri_cek("ornek.pdf", ist, metin="x" * 200, sema=s)

    assert ist.parcalar[0] == s.prompt()
    assert veri["koli_sayisi"] == 1234.5
    assert veri["vade"].strftime("%d.%m.%Y") == "05.03.2024"
