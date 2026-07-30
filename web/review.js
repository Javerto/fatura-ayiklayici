"use strict";
/* Gözden geçirme ekranı. Satırların gerçek (tipli) hâli Python'da durur;
   burada yalnızca metin izdüşümü düzenlenir ve onayda geri gönderilir. */

const R = {
  satirlar: [], alanlar: [], secili: 0,
  haric: new Set(), hatirla: new Set(), duzenlemeler: {},
  sadeceUyarili: false, zoom: 1.0, sayfa: 0, toplamSayfa: 0,
};

// Alan gruplaması yalnızca görsel; anahtar/etiket Python'dan gelir.
const RV_GRUP = [
  ["Fatura",   ["fatura_no", "fatura_tarihi", "tanim"]],
  ["Firma",    ["sirket_adi", "vkn", "vergi_dairesi"]],
  ["Tutarlar", ["kdv_haric_tutar", "vergiler_dahil_tutar", "para_birimi",
                "toplam_miktar", "sira_no"]],
];
const RV_TAM  = new Set(["tanim", "sirket_adi"]);       // tam satır kaplasın
const RV_MONO = new Set(["fatura_no", "vkn"]);          // sabit genişlikli yazı

function reviewAc(o) {
  R.satirlar = o.satirlar;
  R.alanlar = o.alanlar;
  R.secili = 0;
  R.haric.clear(); R.hatirla.clear(); R.duzenlemeler = {};
  R.sadeceUyarili = false;
  $("rvSuzge").textContent = "⚠ Sadece uyarılı";   // durumla birlikte etiket de sıfırlanmalı
  R.zoom = 1.0;

  $("rvAlt").textContent = o.kesildi
    ? "İşlem yarıda kesildi — Onaylayana kadar Excel'e hiçbir şey yazılmaz"
    : "Onaylayana kadar Excel'e hiçbir şey yazılmaz";
  $("anaEkran").hidden = true;
  $("review").hidden = false;
  document.body.style.overflow = "hidden";

  const ilkUyarili = R.satirlar.findIndex(s => s.uyarilar.length);
  R.secili = ilkUyarili >= 0 ? ilkUyarili : 0;
  rvListeCiz();
  rvSatirSec(R.secili);
}

function rvKapat() {
  $("review").hidden = true;
  $("anaEkran").hidden = false;
  document.body.style.overflow = "";
}

// ═══ LİSTE ═══
function rvGorunen() {
  return R.sadeceUyarili
    ? R.satirlar.filter(s => s.uyarilar.length) : R.satirlar;
}

function rvListeCiz() {
  const uyarili = R.satirlar.filter(s => s.uyarilar.length).length;
  const temiz = R.satirlar.length - uyarili;
  $("rvSayi").textContent = `${R.satirlar.length} yeni fatura`;
  $("rvTemiz").textContent = `✓ ${temiz} temiz`;
  $("rvUyarili").hidden = !uyarili;
  $("rvUyarili").textContent = `⚠ ${uyarili} kontrol edilmeli`;

  $("rvListe").innerHTML = rvGorunen().map(s => {
    const uy = s.uyarilar.length, ex = R.haric.has(s.i);
    const tutar = s.form.vergiler_dahil_tutar
      ? `${s.form.vergiler_dahil_tutar} ${s.form.para_birimi || ""}` : "—";
    return `<div class="rvrow ${uy ? "w" : ""} ${ex ? "ex" : ""} ${
      s.i === R.secili ? "on" : ""}" data-i="${s.i}">
      <div class="mk">${ex ? "—" : uy ? "!" : "✓"}</div>
      <div class="g">
        <div class="no">${kacar(s.form.fatura_no || "—")}</div>
        <div class="co">${kacar(s.form.sirket_adi || "—")}</div>
        <div class="am">${ex ? "hariç tutuldu"
          : kacar(tutar) + (s.kaynak ? " · " + kacar(s.kaynak) : "")}</div>
      </div></div>`;
  }).join("") || '<div class="bos">Uyarılı fatura yok.</div>';

  const yazilacak = R.satirlar.length - R.haric.size;
  $("rvYazilacak").textContent = yazilacak
    ? `${yazilacak} fatura yazılacak` : "hiçbir fatura yazılmayacak";
}

// ═══ FORM ═══
function rvSatirSec(i) {
  R.secili = i;
  const s = R.satirlar.find(x => x.i === i);
  if (!s) return;
  const hatali = new Set(s.uyarilar.map(u => u[0]));
  const etiket = Object.fromEntries(R.alanlar.map(a => [a[0], a[1]]));
  const gruplanan = new Set(RV_GRUP.flatMap(g => g[1]));
  const gruplar = RV_GRUP.concat(
    [["Diğer", R.alanlar.map(a => a[0]).filter(a => !gruplanan.has(a))]]);

  $("rvForm").innerHTML = gruplar.filter(([, alanlar]) => alanlar.length).map(
    ([baslik, alanlar]) => `<div class="grp"><span class="lbl">${baslik}</span>
      <div class="fg">${alanlar.filter(a => a in s.form).map(a => `
        <div class="f ${RV_TAM.has(a) ? "tam" : ""} ${RV_MONO.has(a) ? "mono" : ""} ${
          hatali.has(a) ? "bad" : ""}" data-alan="${a}">
          <span>${kacar(etiket[a] || a)}</span>
          <input value="${kacar(s.form[a] || "")}" data-alan="${a}" spellcheck="false">
          ${s.uyarilar.filter(u => u[0] === a).map(u =>
            `<div class="msg"><span>⚠</span><span>${kacar(u[1])}</span></div>`).join("")}
        </div>`).join("")}</div></div>`).join("")
    + `<label class="learn"><input type="checkbox" id="rvHatirla" ${
        R.hatirla.has(i) ? "checked" : ""}>
       <div><div class="t">Bu firma için hatırla</div>
       <div class="d">Şirket adı ve vergi dairesi bu VKN'ye kaydedilir;
         aynı firmanın sonraki faturalarında otomatik düzeltilir.</div></div></label>`;

  $("rvHaric").checked = R.haric.has(i);
  $("rvDosya").textContent = s.dosya;
  R.sayfa = 0;
  rvOnizlemeYukle(true);          // yeni fatura → panele sığdır
  document.querySelectorAll(".rvrow").forEach(r =>
    r.classList.toggle("on", +r.dataset.i === i));
}

/** Uyarıları alanların altına yazar — formu YENİDEN KURMADAN.

    Formu `innerHTML` ile baştan çizmek, kullanıcı Tab'la bir sonraki alana
    geçip yazmaya başladıysa yazdığı karakterleri siliyor ve odağı düşürüyordu. */
function rvUyariGoster(s) {
  const alanBasi = {};
  for (const [alan, mesaj] of s.uyarilar) (alanBasi[alan] ||= []).push(mesaj);

  $("rvForm").querySelectorAll(".f[data-alan]").forEach(f => {
    const mesajlar = alanBasi[f.dataset.alan] || [];
    f.classList.toggle("bad", mesajlar.length > 0);
    f.querySelectorAll(".msg").forEach(e => e.remove());
    for (const m of mesajlar)
      f.insertAdjacentHTML("beforeend",
        `<div class="msg"><span>⚠</span><span>${kacar(m)}</span></div>`);
  });
}

/** Formdaki metinleri toplar; değişiklik varsa kaydeder ve yeniden doğrular. */
async function rvUygula() {
  const s = R.satirlar.find(x => x.i === R.secili);
  if (!s) return;
  const form = {};
  $("rvForm").querySelectorAll("input[data-alan]").forEach(
    e => form[e.dataset.alan] = e.value);
  if (R.alanlar.every(a => (form[a[0]] ?? "") === (s.form[a[0]] ?? ""))) return;

  s.form = form;
  R.duzenlemeler[s.i] = form;
  s.uyarilar = await pywebview.api.satir_dogrula(s.i, form);
  rvListeCiz();
  // Bekleme sırasında başka faturaya geçilmiş olabilir; o durumda formu
  // tazelemek ekranı kullanıcının bıraktığı satıra geri döndürürdü.
  if (R.secili === s.i) rvUyariGoster(s);
}

// ═══ ÖNİZLEME ═══
/** sigdir=true ise ilk çizimden sonra zoom panel genişliğine ayarlanıp
    bir kez daha çizilir (A4 %100'de panele sığmıyor). */
async function rvOnizlemeYukle(sigdir = false) {
  const s = R.satirlar.find(x => x.i === R.secili);
  const pv = $("rvPv");
  if (!s || !s.pdf) {
    pv.innerHTML = '<div class="yok">Bu fatura için PDF önizleme yok<br>(XML veya dosya bulunamadı)</div>';
    $("rvSayfa").textContent = "— / —";
    $("rvZoom").textContent = "—";
    R.toplamSayfa = 0;
    return;
  }
  const c = await pywebview.api.onizleme(s.i, R.sayfa, R.zoom);
  // Yanıt gecikirken başka faturaya geçilmiş olabilir. Bunu kontrol etmezsek
  // panelde A faturasının formu, B faturasının belgesi durur — kullanıcı
  // yanlış belgeye bakarak onay verir.
  if (R.secili !== s.i) return;
  if (c.hata) { pv.innerHTML = `<div class="yok">${kacar(c.hata)}</div>`; return; }

  pv.innerHTML = `<img src="data:image/png;base64,${c.png}" alt="">`;
  R.sayfa = c.sayfa; R.toplamSayfa = c.toplam;
  $("rvSayfa").textContent = `${c.sayfa + 1} / ${c.toplam}`;
  $("rvZoom").textContent = `%${Math.round(R.zoom * 100)}`;
  $("rvOnceki").disabled = c.sayfa === 0;
  $("rvSonraki").disabled = c.sayfa >= c.toplam - 1;

  if (sigdir) {
    const img = pv.querySelector("img");
    const sayfaGenislik = img.naturalWidth / R.zoom;      // 1× hâlindeki genişlik
    const hedef = (pv.clientWidth - 30) / sayfaGenislik;
    const yeni = Math.max(0.5, Math.min(3.0, hedef));
    if (Math.abs(yeni - R.zoom) > 0.05) { R.zoom = yeni; await rvOnizlemeYukle(); }
  }
}

// ═══ UYARILAR ARASI GEZİNME ═══
function rvUyariyaAtla(yon) {
  const n = R.satirlar.length;
  if (!n) return;
  const bas = R.satirlar.findIndex(s => s.i === R.secili);
  for (let adim = 1; adim <= n; adim++) {
    const j = (bas + yon * adim + n * adim) % n;
    if (R.satirlar[j].uyarilar.length) { rvSatirSec(R.satirlar[j].i); return; }
  }
}

// ═══ ONAY / İPTAL ═══
async function rvOnayla() {
  await rvUygula();
  const kalan = R.satirlar.filter(
    s => !R.haric.has(s.i) && s.uyarilar.length).length;
  if (kalan && !await onayModal(
        "Uyarılar var",
        `${kalan} faturada hâlâ uyarı var. Yine de Excel'e yazılsın mı?`,
        "Yine de yaz")) return;

  $("rvOnayla").disabled = true;
  const c = await pywebview.api.review_onayla(
    R.duzenlemeler, [...R.haric], [...R.hatirla]);
  $("rvOnayla").disabled = false;
  if (c.hata) {                 // pencere açık kalır, düzenlemeler kaybolmaz
    await bilgiModal("Excel kaydedilemedi", c.hata);
    return;
  }

  rvKapat();
  const yazilanlar = R.satirlar.filter(s => !R.haric.has(s.i));
  D.uyarilar = yazilanlar.filter(s => s.uyarilar.length)
                         .map(s => ({ dosya: s.dosya, liste: s.uyarilar }));
  // Durum kartı çıkarım anındaki sayıları gösteriyordu; kullanıcı gözden
  // geçirmede uyarıları düzeltince ekranda çelişkili iki sayı kalıyordu.
  D.uyarili = D.uyarilar.length;
  D.ok = yazilanlar.length - D.uyarili;
  bitti({ yazilan: c.yazilan, atlanan: D.atlanan, cikti: c.cikti });
  if (c.dokunulmadi)
    bilgiSatiri("Tüm yeni faturalar hariç tutuldu, Excel'e dokunulmadı.");
  if (c.kural) bilgiSatiri(`${c.kural} firma için düzeltme kuralı kaydedildi.`);
}

async function rvIptal() {
  if ($("rvIptal").disabled) return;      // çift tıklamada ikinci kutu açılmasın
  $("rvIptal").disabled = true;
  const onay = await onayModal(
    "İşlemi iptal et",
    "Çıkarılan veriler ve yaptığınız düzeltmeler kaydedilmeyecek. Emin misiniz?",
    "Evet, iptal et", true);
  $("rvIptal").disabled = false;
  if (!onay) return;
  const c = await pywebview.api.review_iptal();
  rvKapat();
  D.uyarilar = [];
  bilgiSatiri("İşlem iptal edildi, hiçbir şey kaydedilmedi.");
  bitti({ yazilan: 0, atlanan: D.atlanan, cikti: c.cikti });
}

// ═══ BAĞLAMA ═══
function reviewKur() {
  $("rvListe").onclick = e => {
    const r = e.target.closest(".rvrow");
    if (r) { rvUygula().then(() => rvSatirSec(+r.dataset.i)); }
  };
  // Alandan çıkınca uygula: "Uygula" butonuna basmayı unutup değişikliği
  // kaybetmek eski arayüzün en sinsi tuzağıydı.
  $("rvForm").addEventListener("focusout", e => {
    if (e.target.dataset && e.target.dataset.alan) rvUygula();
  });
  $("rvForm").addEventListener("change", e => {
    if (e.target.id === "rvHatirla") {
      e.target.checked ? R.hatirla.add(R.secili) : R.hatirla.delete(R.secili);
    }
  });
  $("rvHaric").onchange = e => {
    e.target.checked ? R.haric.add(R.secili) : R.haric.delete(R.secili);
    rvListeCiz();
  };
  $("rvSuzge").onclick = () => {
    R.sadeceUyarili = !R.sadeceUyarili;
    $("rvSuzge").textContent = R.sadeceUyarili ? "◻ Tümünü göster" : "⚠ Sadece uyarılı";
    rvListeCiz();
  };
  $("rvGeriUyari").onclick = () => rvUyariyaAtla(-1);
  $("rvIleriUyari").onclick = () => rvUyariyaAtla(1);
  $("rvZoomEksi").onclick = () => { R.zoom = Math.max(0.5, R.zoom - 0.25); rvOnizlemeYukle(); };
  $("rvZoomArti").onclick = () => { R.zoom = Math.min(3.0, R.zoom + 0.25); rvOnizlemeYukle(); };
  $("rvOnceki").onclick = () => { R.sayfa--; rvOnizlemeYukle(); };
  $("rvSonraki").onclick = () => { R.sayfa++; rvOnizlemeYukle(); };
  $("rvDisAc").onclick = () => pywebview.api.dosya_ac(R.secili);
  $("rvOnayla").onclick = rvOnayla;
  $("rvIptal").onclick = rvIptal;
}
