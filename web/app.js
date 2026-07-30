"use strict";
const $ = id => document.getElementById(id);

const D = {                 // ekranın tüm durumu
  klasor: "", calisiyor: false, kalite: "1.5",
  toplam: 0, siradaki: 0, ok: 0, uyarili: 0, atlanan: 0,
  paralar: {},              // {TRY: 48320, USD: 120}
  uyarilar: [],             // [{dosya, liste:[...]}]
  baslangic: 0,
};

const SEMBOL = { TRY: "₺", TL: "₺", USD: "$", EUR: "€", GBP: "£" };
const nf = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2,
                                            maximumFractionDigits: 2 });
const para = (t, b) => nf.format(t) + " " + (SEMBOL[b] || b || "");
const kacar = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ═══ GÜNLÜK ═══
function feedTemizle() {
  $("feed").innerHTML =
    '<div class="bos">Henüz işlem yapılmadı.<br>Klasör seçip “İşlemi Başlat”a basın.</div>';
}
function satirEkle(html) {
  const f = $("feed");
  const bos = f.querySelector(".bos");
  if (bos) bos.remove();
  f.insertAdjacentHTML("afterbegin", html);      // en yeni en üstte
  while (f.children.length > 400) f.lastElementChild.remove();
}
function bilgiSatiri(mesaj, tip = "info") {
  satirEkle(`<div class="item ${tip}"><div class="dot">${
    tip === "err" ? "✕" : tip === "warn" ? "!" : "·"}</div>
    <div class="grow">${kacar(mesaj)}</div></div>`);
}

// ═══ DURUM KARTI ═══
function durumTazele() {
  $("stSayi").innerHTML = `${D.siradaki} <span class="of">/ ${D.toplam}</span>`;
  $("stOk").textContent = D.ok;
  $("stWarn").textContent = D.uyarili;
  $("stErr").textContent = D.atlanan;

  const kalemler = Object.entries(D.paralar).filter(([, t]) => t);
  $("stTutar").textContent = kalemler.length
    ? kalemler.map(([b, t]) => para(t, b)).join(" · ") : "—";

  const oran = D.toplam ? (D.siradaki / D.toplam) * 100 : 0;
  $("stFill").style.width = oran + "%";
  $("stFill").classList.toggle("akiyor", D.calisiyor);

  if (!D.calisiyor) return;
  const gecen = (Date.now() - D.baslangic) / 1000;
  if (D.siradaki > 0 && gecen > 2) {
    const kalan = (D.toplam - D.siradaki) * (gecen / D.siradaki);
    $("stEta").textContent = kalan < 60
      ? `~${Math.round(kalan)} sn` : `~${Math.round(kalan / 60)} dk`;
  }
}

// ═══ PYTHON'DAN GELEN OLAYLAR ═══
window.olaylar = function (liste) {
  for (const o of liste) {
    switch (o.t) {
      case "progress": {
        const [su, tp] = o.d;
        D.siradaki = su; D.toplam = tp;
        break;
      }
      case "isleniyor":
        $("stNe").textContent = o.d + " işleniyor…";
        break;
      case "fatura": {
        const f = o.d, uy = f.uyarilar || [];
        if (uy.length) { D.uyarili++; D.uyarilar.push({ dosya: f.dosya, liste: uy }); }
        else D.ok++;
        if (typeof f.tutar === "number") {
          const b = f.para_birimi || "TRY";
          D.paralar[b] = (D.paralar[b] || 0) + f.tutar;
        }
        satirEkle(`<div class="item ${uy.length ? "warn" : "ok"}">
          <div class="dot">${uy.length ? "!" : "✓"}</div>
          <div class="grow">
            <div class="nm">${kacar(f.fatura_no)}</div>
            <div class="co">${kacar(f.sirket_adi)}${
              typeof f.tutar === "number" ? " · " + para(f.tutar, f.para_birimi) : ""}</div>
            ${uy.map(u => `<div class="note">⚠ ${kacar(u[1])}</div>`).join("")}
          </div>
          ${f.kaynak ? `<span class="tag">${kacar(f.kaynak)}</span>` : ""}
          <span class="time">${f.sure != null ? nf.format(f.sure).replace(",00", "") + "s" : ""}</span>
        </div>`);
        break;
      }
      case "atlandi":
        D.atlanan++;
        satirEkle(`<div class="item err"><div class="dot">✕</div>
          <div class="grow"><div class="nm">${kacar(o.d.dosya)}</div>
          <div class="note">${kacar(o.d.sebep)}</div></div>
          <span class="time">—</span></div>`);
        break;
      case "critical":
        bilgiSatiri(o.d, "err");
        break;
      case "warn": case "skip":
        bilgiSatiri(o.d, "warn");
        break;
      case "info":
        bilgiSatiri(o.d.trim());
        break;
      case "review":
        reviewAc(o);
        break;
      case "bitti":
        bitti(o);
        break;
    }
  }
  durumTazele();
};

function bitti(o) {
  D.calisiyor = false;
  $("stNe").textContent = o.hata ? "Excel kaydedilemedi" : "tamamlandı";
  $("stEta").textContent = "—";
  $("btnBasla").disabled = false;
  $("btnDurdur").disabled = true;
  $("btnExcel").disabled = !o.cikti;
  $("btnRetry").disabled = !o.atlanan;
  $("btnRetry").textContent = o.atlanan ? `↺ Yeniden Dene · ${o.atlanan}` : "↺ Yeniden Dene";
  $("btnUyari").disabled = !D.uyarilar.length;
  $("btnUyari").textContent = D.uyarilar.length
    ? `⚠ Uyarılar · ${D.uyarilar.reduce((t, u) => t + u.liste.length, 0)}`
    : "⚠ Uyarılar";

  if (o.hata) bilgiSatiri("Excel kaydedilemedi: " + o.hata, "err");
  else if (o.yazilan) bilgiSatiri(`Excel oluşturuldu — ${o.yazilan} yeni fatura yazıldı.`);
}

// ═══ MODAL ═══
function modal(html, genis) {
  const p = document.createElement("div");
  p.className = "perde";
  p.innerHTML = `<div class="modal${genis ? " genis" : ""}">${html}</div>`;
  p.addEventListener("click", e => { if (e.target === p) p.remove(); });
  document.body.appendChild(p);
  return p;
}

/* Tarayıcının confirm/alert kutuları WebView2'de "127.0.0.1:… diyor ki"
   başlığıyla çıkıyor; kendi kutularımızı kullanıyoruz. */
function onayModal(baslik, mesaj, evetEtiket = "Devam et", tehlikeli = false) {
  return new Promise(cevapla => {
    const p = modal(`
      <h2>${kacar(baslik)}</h2>
      <div class="aciklama">${kacar(mesaj)}</div>
      <div class="alt">
        <button class="btn-sec" id="oHayir">Vazgeç</button>
        <button class="${tehlikeli ? "btn-sec err" : "btn-primary"}" id="oEvet">${kacar(evetEtiket)}</button>
      </div>`);
    const kapat = c => { p.remove(); cevapla(c); };
    $("oHayir").onclick = () => kapat(false);
    $("oEvet").onclick = () => kapat(true);
    p.addEventListener("click", e => { if (e.target === p) kapat(false); });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { document.removeEventListener("keydown", esc); kapat(false); }
    });
    $("oEvet").focus();
  });
}

function bilgiModal(baslik, mesaj) {
  return new Promise(cevapla => {
    const p = modal(`
      <h2>${kacar(baslik)}</h2>
      <div class="aciklama">${kacar(mesaj)}</div>
      <div class="alt"><button class="btn-primary" id="bTamam">Tamam</button></div>`);
    const kapat = () => { p.remove(); cevapla(); };
    $("bTamam").onclick = kapat;
    p.addEventListener("click", e => { if (e.target === p) kapat(); });
    $("bTamam").focus();
  });
}

function apiKeyModal() {
  const p = modal(`
    <h2>Google AI API Anahtarı</h2>
    <div class="aciklama">aistudio.google.com → “Get API Key” adresinden ücretsiz alabilirsiniz.</div>
    <div class="icerik">
      <div class="field"><input id="mKey" type="password" placeholder="AIza…" spellcheck="false"></div>
      <div class="hata" id="mHata"></div>
    </div>
    <div class="alt">
      <button class="btn-sec" id="mIptal">Vazgeç</button>
      <button class="btn-primary" id="mKaydet">Kaydet</button>
    </div>`);
  $("mKey").focus();
  $("mIptal").onclick = () => p.remove();
  $("mKaydet").onclick = async () => {
    const k = $("mKey").value.trim();
    if (!k) { $("mHata").textContent = "Anahtar boş olamaz."; return; }
    if (await pywebview.api.api_key_kaydet(k)) { apiDurumTazele(true); p.remove(); }
    else $("mHata").textContent = "Kaydedilemedi.";
  };
  $("mKey").onkeydown = e => { if (e.key === "Enter") $("mKaydet").click(); };
}

async function gecmisModal() {
  const kayitlar = await pywebview.api.gecmis();
  modal(`
    <h2>İşlem Geçmişi</h2>
    <div class="aciklama">Son ${kayitlar.length} çalışma.</div>
    <div class="icerik">${kayitlar.length ? `
      <table><thead><tr><th>Tarih</th><th>Klasör</th><th>Dosya</th>
        <th>İşlenen</th><th>Atlanan</th><th>Süre</th></tr></thead><tbody>
        ${kayitlar.map(k => `<tr><td>${kacar(k.tarih)}</td><td>${kacar(k.klasor)}</td>
          <td>${kacar(k.dosya)}</td><td>${k.islenen}</td><td>${k.atlanan}</td>
          <td>${k.sure_dk} dk</td></tr>`).join("")}
      </tbody></table>` : '<div class="bos">Henüz kayıt yok.</div>'}
    </div>
    <div class="alt"><button class="btn-sec" onclick="this.closest('.perde').remove()">Kapat</button></div>
  `, true);
}

function uyariModal() {
  const toplam = D.uyarilar.reduce((t, u) => t + u.liste.length, 0);
  modal(`
    <h2>Veri Uyarıları</h2>
    <div class="aciklama">${toplam} uyarı, ${D.uyarilar.length} fatura.
      Bu uyarılar işlemi durdurmaz; kontrol edilmesi önerilen alanları gösterir.</div>
    <div class="icerik">${D.uyarilar.map(u => `
      <div class="uy-grup"><div class="dosya">${kacar(u.dosya)}</div>
        ${u.liste.map(x => `<div class="u">⚠ ${kacar(x[1])}</div>`).join("")}</div>`).join("")}
    </div>
    <div class="alt"><button class="btn-sec" onclick="this.closest('.perde').remove()">Kapat</button></div>
  `, true);
}

// ═══ EYLEMLER ═══
function apiDurumTazele(var_mi) {
  const e = $("apiDurum");
  e.textContent = var_mi ? "API anahtarı tanımlı" : "API anahtarı gerekli — 🔑 ile ekleyin";
  e.classList.toggle("yok", !var_mi);
}

async function klasorGoster(yol) {
  D.klasor = yol;
  $("klasorYol").textContent = yol;
  $("klasorYol").classList.remove("bos");
  const o = await pywebview.api.klasor_ozeti(yol);
  const t = o.pdf + o.xml;
  $("klasorMeta").innerHTML = t
    ? `<b>${t} dosya</b> bulundu · ${o.pdf} PDF · ${o.xml} XML`
    : "Bu klasörde PDF veya XML bulunamadı";
}

async function klasorSec() {
  const yol = await pywebview.api.klasor_sec();
  if (yol) klasorGoster(yol);
}

async function basla(retry) {
  const cevap = retry
    ? await pywebview.api.yeniden_dene()
    : await pywebview.api.basla({ klasor: D.klasor, cikti: $("ciktiAd").value,
                                  kalite: D.kalite });
  if (cevap.hata === "api_key") { apiKeyModal(); return; }
  if (cevap.hata) { bilgiSatiri(cevap.hata, "err"); return; }

  Object.assign(D, { calisiyor: true, siradaki: 0, toplam: 0, ok: 0, uyarili: 0,
                     atlanan: 0, paralar: {}, uyarilar: [], baslangic: Date.now() });
  feedTemizle();
  $("stNe").textContent = "hazırlanıyor…";
  $("stEta").textContent = "—";
  $("btnBasla").disabled = true;
  $("btnDurdur").disabled = false;
  $("btnUyari").disabled = true;
  $("btnRetry").disabled = true;
  $("btnExcel").disabled = true;
  durumTazele();
}

// ═══ AÇILIŞ ═══
async function acilis() {
  const d = await pywebview.api.baslangic_durumu();
  document.documentElement.dataset.tema = d.tema;
  temaKur("btnTema", "temaWrap", t => pywebview.api.tema_kaydet(t));
  apiDurumTazele(d.api_key_var);

  D.kalite = d.kalite;
  $("kaliteSeg").querySelectorAll("button").forEach(b =>
    b.classList.toggle("on", b.dataset.k === d.kalite));

  $("btnKlasor").onclick = klasorSec;
  $("klasorKart").onclick = e => { if (e.target.id !== "btnKlasor") klasorSec(); };
  $("btnBasla").onclick = () => basla(false);
  $("btnRetry").onclick = () => basla(true);
  $("btnDurdur").onclick = () => {
    pywebview.api.durdur();
    $("btnDurdur").disabled = true;
    $("stNe").textContent = "durduruluyor — işlenen fatura tamamlanıyor…";
  };
  $("btnExcel").onclick = () => pywebview.api.excel_ac();
  $("btnKey").onclick = apiKeyModal;
  $("btnGecmis").onclick = gecmisModal;
  $("btnUyari").onclick = uyariModal;
  $("btnTemizle").onclick = feedTemizle;
  $("kaliteSeg").onclick = e => {
    if (!e.target.dataset.k) return;
    D.kalite = e.target.dataset.k;
    $("kaliteSeg").querySelectorAll("button").forEach(b => b.classList.remove("on"));
    e.target.classList.add("on");
    pywebview.api.kalite_kaydet(D.kalite);
  };

  reviewKur();
  if (d.klasor) klasorGoster(d.klasor);       // son kullanılan klasör
  if (!d.api_key_var) setTimeout(apiKeyModal, 400);
}

// pywebviewready, app.js dinleyiciyi kurmadan önce tetiklenmiş olabilir;
// o durumda olay bir daha gelmez ve arayüz bağlanmadan ölü kalır.
function acilisiBaslat() {
  acilis().catch(e => {
    $("apiDurum").textContent = "Arayüz başlatılamadı: " + e;
    $("apiDurum").classList.add("yok");
  });
}
if (window.pywebview && window.pywebview.api) acilisiBaslat();
else window.addEventListener("pywebviewready", acilisiBaslat);
