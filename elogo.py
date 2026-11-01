"""eLogo iç API'sine giden tek kapı."""

import base64
import http.client
import json
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from hatalar import ElogoHatasi, ElogoOturumHatasi


TABAN_URL = "https://customerapi-edevlet.elogo.com.tr"
# ponytail: rowOffset'in satır sayısı olması ve 100'lük parçanın kabul edilmesi
# canlıda doğrulanmamış varsayımlar (spike en fazla 2 numara denedi); doğrulama #17'de.
PARCA_BOYU = 100


class _YonlendirmeyiIzleme(HTTPRedirectHandler):
    """urllib yönlendirmede Authorization başlığını yeni adrese de taşır; token
    başka bir host'a gitmesin diye izlenmez. 3xx, durum koduyla hata olarak döner."""

    def redirect_request(self, *args, **kwargs):
        return None


_acici = build_opener(_YonlendirmeyiIzleme)


def _varsayilan_gonder(yontem, url, govde, basliklar):
    istek = Request(url, data=govde, headers=basliklar, method=yontem)
    try:
        with _acici.open(istek, timeout=60) as yanit:
            return yanit.status, yanit.read()
    except HTTPError as hata:
        return hata.code, hata.read()


class ElogoIstemcisi:
    def __init__(self, token, customer_id, *, son_kullanma,
                 gonder=_varsayilan_gonder, saat=time.time):
        self._token = token
        self._customer_id = customer_id
        self._son_kullanma = son_kullanma
        self._gonder = gonder
        self._saat = saat

    def __repr__(self):
        return (f"ElogoIstemcisi(customer_id={self._customer_id!r}, "
                f"son_kullanma={self._son_kullanma!r})")

    def fatura_bul(self, nolar):
        anahtarlar = {}
        for no in nolar:
            anahtar = no.casefold()
            if anahtar not in anahtarlar:
                anahtarlar[anahtar] = no
        if not anahtarlar:
            return {}

        sonuc = {no: [] for no in anahtarlar.values()}
        sirali_nolar = list(anahtarlar.values())
        for baslangic in range(0, len(sirali_nolar), PARCA_BOYU):
            parca = sirali_nolar[baslangic:baslangic + PARCA_BOYU]
            self._fatura_parcasini_bul(parca, anahtarlar, sonuc)
        return sonuc

    def _fatura_parcasini_bul(self, parca, anahtarlar, sonuc):
        row_offset = 0
        while True:
            govde = {
                "selectedPdfCreationtype": False,
                "rowOffset": row_offset,
                "pageSize": PARCA_BOYU,
                "customerIds": [self._customer_id],
                "invoiceNumbers": parca,
                "erpDocumentNumbers": [],
                "peopleInterestedInInvoice": [],
                "receiverFinancialIds": [],
                "senderFinancialIds": [],
                "invoiceIds": [],
                "AllInvoiceGroupsWhichTheUserIsIncluded": [],
                "envelopeIds": [],
                "selectedApprovalStatues": None,
                "erpTransportationState": -1,
                "recognitionState": -1,
                "invoiceScenario": -1,
                "invoiceType": -1,
                "sortfield": None,
                "sortOrder": 1,
                "selectedFilter": 2,
                "selectedInvoiceGroup": None,
                "selectedUserGroups": None,
                "freeTextSearchForTaxPayers": [],
                "DocumentType": 1,
                "storageLocation": 0,
            }
            veri = self._istek("POST", f"{TABAN_URL}/invoice/load",
                               json.dumps(govde).encode("utf-8"), True)
            items = veri.get("Items")
            total = veri.get("TotalCount")
            if (not isinstance(items, list) or isinstance(total, bool)
                    or not isinstance(total, int) or total < 0
                    or len(items) > total):
                raise ElogoHatasi("eLogo fatura listesi geçersiz.")
            for item in items:
                if not isinstance(item, dict) or "InvoiceNumber" not in item:
                    raise ElogoHatasi("eLogo fatura öğesi geçersiz.")
                no_anahtari = item["InvoiceNumber"].casefold() \
                    if isinstance(item["InvoiceNumber"], str) else None
                if no_anahtari in anahtarlar:
                    sonuc[anahtarlar[no_anahtari]].append(item)
            if row_offset + len(items) >= total:
                return
            if not items:
                raise ElogoHatasi("eLogo fatura listesi boş sayfa döndürdü.")
            row_offset += len(items)

    def xml_indir(self, invoice_id):
        url = (f"{TABAN_URL}/invoice/GenerateView?invoiceId="
               f"{quote(invoice_id, safe='')}&location=0&resultFormat=2")
        veri = self._istek("GET", url, None, False)
        payload = veri.get("Payload")
        if not isinstance(payload, dict) or payload.get("IsSuccess") is not True:
            raise ElogoHatasi("eLogo XML yanıtı başarısız.")
        document = payload.get("Document")
        if not isinstance(document, str):
            raise ElogoHatasi("eLogo XML belgesi eksik.")
        try:
            return base64.b64decode(document, validate=True)
        except (ValueError, TypeError):
            raise ElogoHatasi("eLogo XML belgesi bozuk.") from None

    def _istek(self, yontem, url, govde, json_govde):
        if self._saat() >= self._son_kullanma:
            raise ElogoOturumHatasi("eLogo oturumunun süresi doldu.")
        basliklar = {"Authorization": f"Bearer {self._token}"}
        if json_govde:
            basliklar["Content-Type"] = "application/json"
        try:
            durum, yanit = self._gonder(yontem, url, govde, basliklar)
        except (OSError, http.client.HTTPException):
            raise ElogoHatasi("eLogo'ya bağlanılamadı.") from None
        if durum != 200:
            if self._saat() >= self._son_kullanma - 60:
                raise ElogoOturumHatasi(
                    f"eLogo oturumu geçersiz (durum kodu: {durum}).")
            raise ElogoHatasi(f"eLogo isteği başarısız (durum kodu: {durum}).")
        try:
            veri = json.loads(yanit.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError):
            raise ElogoHatasi("eLogo yanıtı JSON değil.") from None
        if not isinstance(veri, dict):
            raise ElogoHatasi("eLogo yanıtı nesne değil.")
        if veri.get("Success") is False:
            raise ElogoHatasi("eLogo isteği başarısız oldu.")
        return veri
