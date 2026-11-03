"use strict";
/* Gözden geçirme ekranı. Satırların gerçek (tipli) hâli Python'da durur;
   burada yalnızca metin izdüşümü düzenlenir ve onayda geri gönderilir. */

const R = {
  satirlar: [], alanlar: [], secili: 0,
  haric: new Set(), hatirla: new Set(), duzenlemeler: {},
  sadeceUyarili: false, zoom: 1.0, sayfa: 0, toplamSayfa: 0,
  sigdir: false, yukleNo: 0,   // açılışta panele sığdır; yalnız son önizleme isteği geçerli
  vurgu: null, vurguNo: 0,     // {sayfa, kutular}; yalnız son arama geçerli
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
  // Önce şüpheliler. Yalnızca açılışta sıralanır: düzeltme sırasında yeniden
  // sıralansa, uyarısı giden satır kullanıcının elinin altından kayardı.
  R.satirlar = [...o.satirlar].sort((a, b) => !a.uyarilar.length - !b.uyarilar.length);
  R.alanlar = o.alanlar;
  // Taslaktan dönülünce önceki düzeltmeler ve hariçler gelir; onayda yeniden gönderilmeli.
  R.haric = new Set(o.haric || []); R.hatirla.clear();
  R.duzenlemeler = { ...(o.duzenlemeler || {}) };
  R.sadeceUyarili = false;
  $("rvSuzge").textContent = "⚠ Sadece uyarılı";   // durumla birlikte etiket de sıfırlanmalı
  R.zoom = 1.0;

  $("rvAlt").textContent = o.kesildi
    ? "İşlem yarıda kesildi — Onaylayana kadar Excel'e hiçbir şey yazılmaz"
    : "Onaylayana kadar Excel'e hiçbir şey yazılmaz";
  rvSemaFarki(o.sema_farki);
  $("anaEkran").hidden = true;
  $("review").hidden = false;
  document.body.style.overflow = "hidden";

  R.secili = R.satirlar.length ? R.satirlar[0].i : 0;
  rvListeCiz();
  rvSatirSec(R.secili);
}

// Koşu düzeyinde uyarı: arşiv başka bir alan setiyle yazılmış. Bir satıra ait
// değil, o yüzden (alan, mesaj) listesine değil üst şeride yazılır.
function rvSemaFarki(f) {
  const el = $("rvSema");
  el.hidden = !f;
  if (!f) return;
  const parcalar = [];
  if (f.arsivde_fazla.length)
    parcalar.push(`şu anki alanlarda olmayan ${f.arsivde_fazla.length} sütun korunuyor (${f.arsivde_fazla.join(", ")}) — eski verisi durur, yeni faturalarda boş kalır`);
  if (f.yeni.length)
    parcalar.push(`eklenecek ${f.yeni.length} yeni sütun (${f.yeni.join(", ")})`);
  el.textContent = `⚠ Bu Excel farklı bir alan setiyle oluşturulmuş: ${parcalar.join(" · ")}`;
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
  // Odak bırakılmazsa aşağıdaki `innerHTML` odaklı alanı silerken `focusout`
  // üretir; o anda R.secili yeni satır, formda ise hâlâ eski satırın metinleri
  // olduğundan rvUygula eski satırın değerlerini YENİ satıra yazar.
  if ($("rvForm").contains(document.activeElement)) document.activeElement.blur();
  R.secili = i;
  const s = R.satirlar.find(x => x.i === i);
  if (!s) return;
  const hatali = new Set(s.uyarilar.map(u => u[0]));
  const etiket = Object.fromEntries(R.alanlar.map(a => [a[0], a[1]]));
  const gruplanan = new Set(RV_GRUP.flatMap(g => g[1]));
  // Grup sabit, grup İÇİ sıra şemanın sırası: editörde sıra değişince form da değişsin.
  const sirali = R.alanlar.map(a => a[0]);
  const gruplar = RV_GRUP.map(([b, g]) => [b, sirali.filter(a => g.includes(a))]).concat(
    [["Diğer", sirali.filter(a => !gruplanan.has(a))]]);

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
  R.sigdir = true;                // yeni fatura → panele sığdır
  rvVurguTemizle();
  rvOnizlemeYukle();
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
/** R.sigdir ise ilk çizimden sonra zoom panel genişliğine ayarlanıp
    bir kez daha çizilir (A4 %100'de panele sığmıyor). */
async function rvOnizlemeYukle() {
  const s = R.satirlar.find(x => x.i === R.secili);
  const pv = $("rvPv");
  const no = ++R.yukleNo;
  if (!s || !(s.pdf || s.xml)) return rvOnizlemeYok("Bu fatura için önizleme yok\n(dosya bulunamadı)");
  const c = await pywebview.api.onizleme(s.i, R.sayfa, R.zoom);
  // Yanıt gecikirken başka faturaya, sayfaya veya zoom'a geçilmiş olabilir. Bunu
  // kontrol etmezsek panelde A faturasının formu, B faturasının belgesi durur —
  // kullanıcı yanlış belgeye bakarak onay verir.
  if (no !== R.yukleNo) return;
  if (c.hata) return rvOnizlemeYok(c.hata);
  if (c.html) return rvXmlGoster(c.html, no);

  pv.innerHTML = `<div class="pv-sayfa"><img src="data:image/png;base64,${c.png}" alt=""></div>`;
  R.sayfa = c.sayfa; R.toplamSayfa = c.toplam;
  $("rvSayfa").textContent = `${c.sayfa + 1} / ${c.toplam}`;
  $("rvZoom").textContent = `%${Math.round(R.zoom * 100)}`;
  $("rvOnceki").disabled = c.sayfa === 0;
  $("rvSonraki").disabled = c.sayfa >= c.toplam - 1;

  // Çözülmeden görselin boyutu 0: sığdırma sonsuz zoom hesaplar (%300'e kaçar),
  // işaretin yeri de ölçülemez ve panel ona kaydırılamaz.
  const img = pv.querySelector("img");
  await img.decode().catch(() => {});
  if (no !== R.yukleNo || !img.naturalWidth) return;

  if (R.sigdir) {
    R.sigdir = false;
    const sayfaGenislik = img.naturalWidth / R.zoom;      // 1× hâlindeki genişlik
    const hedef = (pv.clientWidth - 30) / sayfaGenislik;
    const yeni = Math.max(0.5, Math.min(3.0, hedef));
    if (Math.abs(yeni - R.zoom) > 0.05) { R.zoom = yeni; return rvOnizlemeYukle(); }
  }
  rvVurguCiz();
}

function rvOnizlemeYok(mesaj) {
  $("rvPv").innerHTML = `<div class="yok">${kacar(mesaj)}</div>`;
  $("rvSayfa").textContent = "— / —";
  $("rvZoom").textContent = "—";
  $("rvOnceki").disabled = $("rvSonraki").disabled = true;
  R.toplamSayfa = 0;
}

/** XML görüntüsünü gösterir. Şablon faturayı kesenden gelir, çıktısı güvenilmez:
    betik çalışmaz (sandbox) ve dışarıya istek gidemez (CSP). `allow-same-origin`
    yalnızca buradan işaretleme yapabilmek için; betik olmadan çerçeveye yetki vermez. */
async function rvXmlGoster(html, no) {
  const pv = $("rvPv");
  // DOMParser başı garanti eder: şablon <head>'den önce içerik yazsa bile kural en
  // başa girer (gövdeye düşen CSP etiketi yok sayılırdı). Burada hiçbir şey yüklenmez.
  const belge = new DOMParser().parseFromString(html, "text/html");
  belge.querySelectorAll("meta[http-equiv], base").forEach(e => e.remove());
  const csp = belge.createElement("meta");
  csp.httpEquiv = "Content-Security-Policy";
  csp.content = "default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'";
  belge.head.prepend(csp);

  const f = document.createElement("iframe");
  f.className = "pv-xml";
  f.title = "Fatura görüntüsü";
  f.setAttribute("sandbox", "allow-same-origin");
  f.srcdoc = (belge.doctype ? "<!doctype html>" : "") + belge.documentElement.outerHTML;
  const yuklendi = new Promise(r => { f.onload = r; });
  pv.replaceChildren(f);
  await yuklendi;
  if (no !== R.yukleNo) return;

  const d = f.contentDocument;
  f.classList.add("hazir");
  d.addEventListener("click", e => e.preventDefault());    // bağlantı çerçeveyi dışarı götürmesin
  if (R.sigdir) {
    R.sigdir = false;
    d.documentElement.style.zoom = 1;
    R.zoom = Math.max(0.5, Math.min(3.0, f.clientWidth / Math.max(d.documentElement.scrollWidth, 1)));
  }
  d.documentElement.style.zoom = R.zoom;
  R.sayfa = 0; R.toplamSayfa = 1;
  $("rvSayfa").textContent = "1 / 1";
  $("rvZoom").textContent = `%${Math.round(R.zoom * 100)}`;
  $("rvOnceki").disabled = $("rvSonraki").disabled = true;
  rvVurguCiz();
}

// ═══ DEĞERİ BELGEDE GÖSTERME ═══
function rvVurguTemizle() {
  R.vurgu = null;
  R.vurguNo++;                    // yoldaki arama sonucu artık geçersiz
  $("rvVurguNot").hidden = true;
}

/** Alana girilince değeri kaynak belgede bulur, gerekirse sayfasına geçip işaretler. */
async function rvVurgula(alan, metin) {
  const s = R.satirlar.find(x => x.i === R.secili);
  if (!s || !(s.pdf || s.xml)) return;
  const no = ++R.vurguNo;
  const c = await pywebview.api.deger_bul(s.i, alan, metin, R.sayfa);
  if (no !== R.vurguNo) return;
  R.vurgu = metin.trim() ? c : null;
  $("rvVurguNot").textContent = s.kaynak === "OCR"
    ? "Taranmış belgede değer işaretlenemez" : "Bu değer belgede bulunamadı";
  if (c.kutular && c.sayfa !== R.sayfa) {
    R.sayfa = c.sayfa;
    $("rvVurguNot").hidden = true;
    return rvOnizlemeYukle();     // çizim yüklemenin sonunda yapılır
  }
  rvVurguCiz();
}

/** XML görüntüsünde değeri işaretler. PDF'teki `_tam_kelime` ile aynı kural. */
function rvXmlVurguCiz(f) {
  const d = f.contentDocument, w = f.contentWindow;
  if (!d || !d.body) return false;
  d.querySelectorAll("mark[data-vurgu]").forEach(m => m.replaceWith(...m.childNodes));
  d.body.normalize();
  if (!R.vurgu || !R.vurgu.metinler) return false;

  for (const metin of R.vurgu.metinler) {
    const kacis = metin.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const desen = new RegExp(R.vurgu.tam
      ? `(?<![\\p{L}\\p{N}_.,])${kacis}(?![\\p{L}\\p{N}_]|[.,]\\d)` : kacis, "giu");
    const gezgin = d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT);
    const dugumler = [];
    while (gezgin.nextNode()) if (gezgin.currentNode.parentElement.closest("style,script") === null)
      dugumler.push(gezgin.currentNode);
    const isaretler = [];
    for (const n of dugumler) {
      // Sondan başa: öndeki eşleşmelerin konumu bozulmasın.
      for (const m of [...n.data.matchAll(desen)].reverse()) {
        const a = d.createRange();
        a.setStart(n, m.index);
        a.setEnd(n, m.index + m[0].length);
        const isaret = d.createElement("mark");    // tarayıcının sarısı: temadan bağımsız sayfa
        isaret.dataset.vurgu = "1";
        a.surroundContents(isaret);
        isaretler.unshift(isaret);
      }
    }
    if (isaretler.length) {
      const b = isaretler[0].getBoundingClientRect();
      w.scrollBy(b.left + b.width / 2 - w.innerWidth / 2, b.top + b.height / 2 - w.innerHeight / 2);
      return true;
    }
  }
  return false;
}

/** R.vurgu: null = aranan yok; {} = bulunamadı; {sayfa, kutular} = PDF; {metinler, tam} = XML.
    Her önizleme yüklemesinin sonunda da çağrılır. Görüntü henüz yüklenirken XML'de sonuç
    bilinmez: "bulunamadı" notu ancak görüntü hazırsa verilir. */
function rvVurguCiz() {
  const pv = $("rvPv"), v = R.vurgu, cerceve = pv.querySelector("iframe");
  let not = !!v && !v.kutular;
  if (cerceve) {
    not = cerceve.classList.contains("hazir") && !rvXmlVurguCiz(cerceve) && !!v;
  } else {
    if (v && v.metinler) not = false;             // eski belge duruyor, XML yolda
    rvPdfVurguCiz();
  }
  $("rvVurguNot").hidden = !not;
}

/** Kutular oransal: görsele yüzdeyle oturur, zoom değişince hesap gerekmez. */
function rvPdfVurguCiz() {
  const pv = $("rvPv"), kap = pv.querySelector(".pv-sayfa");
  if (!kap) return;
  kap.querySelectorAll(".vurgu").forEach(e => e.remove());
  if (!R.vurgu || !R.vurgu.kutular || R.vurgu.sayfa !== R.sayfa) return;
  kap.insertAdjacentHTML("beforeend", R.vurgu.kutular.map(([x, y, g, h]) =>
    `<div class="vurgu" style="left:${x * 100}%;top:${y * 100}%;width:${g * 100}%;height:${h * 100}%"></div>`
  ).join(""));
  // scrollIntoView değil: o, dış kapları da kaydırıp ekran düzenini kaçırabilir.
  const b = kap.querySelector(".vurgu").getBoundingClientRect();
  const p = pv.getBoundingClientRect();
  pv.scrollBy(b.left + b.width / 2 - p.left - p.width / 2,
              b.top + b.height / 2 - p.top - p.height / 2);
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

// ═══ KLAVYE ═══
/** Görünen listede bir önceki/sonraki satıra geçer ve yazmaya hazır bırakır. */
async function rvSatiraGec(yon) {
  const gorunen = rvGorunen();
  const hedef = gorunen[gorunen.findIndex(s => s.i === R.secili) + yon];
  if (!hedef) return;
  await rvUygula();
  rvSatirSec(hedef.i);
  document.querySelector(".rvrow.on")?.scrollIntoView({ block: "nearest" });
  ($("rvForm").querySelector(".f.bad input") ||
   $("rvForm").querySelector("input[data-alan]"))?.focus();
}

function rvKlavye(e) {
  if ($("review").hidden || document.querySelector(".perde")) return;
  if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
    e.preventDefault();
    rvSatiraGec(e.key === "ArrowUp" ? -1 : 1);
  } else if (e.altKey && e.key.toLowerCase() === "h") {
    e.preventDefault();
    $("rvHaric").click();
  } else if (e.ctrlKey && e.key === "Enter" && !e.repeat) {
    e.preventDefault();
    rvOnayla();
  }
}

// ═══ ONAY / İPTAL ═══
async function rvOnayla() {
  // Kısayol butonu atlar: kilit, ilk `await`ten önce konmazsa ikinci basış
  // araya girip ikinci bir onay kutusu açar.
  if ($("rvOnayla").disabled) return;
  $("rvOnayla").disabled = true;
  let c;
  try {
    await rvUygula();
    const kalan = R.satirlar.filter(
      s => !R.haric.has(s.i) && s.uyarilar.length).length;
    if (kalan && !await onayModal(
          "Uyarılar var",
          `${kalan} faturada hâlâ uyarı var. Yine de Excel'e yazılsın mı?`,
          "Yine de yaz")) return;
    c = await pywebview.api.review_onayla(
      R.duzenlemeler, [...R.haric], [...R.hatirla]);
  } finally {
    $("rvOnayla").disabled = false;
  }
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
  if (c.kural_hatasi) bilgiSatiri(c.kural_hatasi, "warn");
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
  $("rvForm").addEventListener("focusin", e => {
    if (e.target.dataset && e.target.dataset.alan)
      rvVurgula(e.target.dataset.alan, e.target.value);
  });
  $("rvForm").addEventListener("change", e => {
    if (e.target.id === "rvHatirla") {
      e.target.checked ? R.hatirla.add(R.secili) : R.hatirla.delete(R.secili);
    } else if (e.target.dataset && e.target.dataset.alan && document.activeElement === e.target) {
      rvVurgula(e.target.dataset.alan, e.target.value);   // Enter ile değiştirildi
    }
  });
  $("rvHaric").onchange = e => {
    e.target.checked ? R.haric.add(R.secili) : R.haric.delete(R.secili);
    pywebview.api.review_haric(R.secili, e.target.checked);   // taslağa
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
  document.addEventListener("keydown", rvKlavye);
  $("rvIptal").onclick = rvIptal;
}
