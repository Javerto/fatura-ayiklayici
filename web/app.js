"use strict";
const $ = id => document.getElementById(id);

const D = {                 // ekranın tüm durumu
  klasor: "", calisiyor: false, kalite: "1.5",
  toplam: 0, siradaki: 0, ok: 0, uyarili: 0, atlanan: 0,
  paralar: {},              // {TRY: 48320, USD: 120}
  uyarilar: [],             // [{dosya, liste:[...]}]
  ucan: new Map(),          // o an işlenen dosyalar: dosya → tip
  durduruluyor: false,      // durdurma mesajı uçan-liste tarafından ezilmesin
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
/* MAX_WORKERS=5 olduğu için aynı anda birden fazla dosya uçuyor; tek satır
   göstermek hangisinin görüneceğini rastgeleye bırakıyordu. */
function ucanTazele() {
  if (D.durduruluyor || !D.calisiyor) return;   // "Durduruluyor…"/"Tamamlandı" korunsun
  const kutu = $("stUcan");
  if (!D.ucan.size) {
    // Son dosya bitti, yenisi henüz başlamadı: eski listeyi asılı bırakma.
    $("stNe").textContent = "Sıradaki Fatura Hazırlanıyor…";
    kutu.hidden = true;
    return;
  }
  $("stNe").textContent = `${D.ucan.size} Dosya İşleniyor`;
  kutu.innerHTML = [...D.ucan].map(([dosya, tip]) =>
    `<div class="sat"><span class="nokta"></span><span class="ad">${kacar(dosya)}</span>${
      tip ? `<span class="tip">${kacar(tip)}</span>` : ""}</div>`).join("");
  kutu.hidden = false;
}

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
        D.ucan.set(o.d.dosya, o.d.tip);
        break;
      case "fatura": {
        const f = o.d, uy = f.uyarilar || [];
        D.ucan.delete(f.dosya);
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
        D.ucan.delete(o.d.dosya);
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
      case "elogo_satir": {
        const e = o.d;
        const tip = e.durum === "indirildi" ? "ok" : e.durum === "atlandi" ? "warn" : "err";
        satirEkle(`<div class="item ${tip}">
          <div class="dot">${{ ok: "✓", warn: "!", err: "✕" }[tip]}</div>
          <div class="grow"><div class="nm">${kacar(e.no)}</div>
          <div class="note">${kacar(e.mesaj)}</div></div></div>`);
        break;
      }
      case "elogo_ozet":
        elogoBitti(o.d);
        break;
      case "review":
        reviewAc(o);
        break;
      case "bitti":
        bitti(o);
        break;
    }
  }
  ucanTazele();
  durumTazele();
};

function bitti(o) {
  D.calisiyor = false;
  D.ucan.clear();
  D.durduruluyor = false;
  $("stUcan").hidden = true;
  $("stNe").textContent = o.hata ? "Excel Kaydedilemedi" : "Tamamlandı";
  $("stEta").textContent = "—";
  $("btnBasla").disabled = false;
  $("btnElogo").disabled = false;
  $("btnAlanlar").disabled = false;
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

function elogoBitti(o) {
  D.calisiyor = false;
  D.durduruluyor = false;
  $("stNe").textContent = o.durduruldu ? "Durduruldu" : o.hata ? "Durdu" : "Tamamlandı";
  $("stEta").textContent = "—";
  $("btnBasla").disabled = false;
  $("btnElogo").disabled = false;
  $("btnAlanlar").disabled = false;
  $("btnDurdur").disabled = true;
  if (D.klasor) klasorGoster(D.klasor);       // inen XML'ler sayaca yansısın
  if (o.hata) bilgiSatiri(o.hata, "err");

  const bolum = (baslik, liste) => liste.length ? `
    <div class="uy-grup"><div class="dosya">${kacar(baslik)} · ${liste.length}</div>
      <div class="u">${liste.map(kacar).join("<br>")}</div></div>` : "";
  const p = modal(`
    <h2>eLogo indirme özeti</h2>
    ${o.hata ? `<div class="aciklama">${kacar(o.hata)}</div>` : ""}
    <div class="icerik">
      ${bolum("İndirilen", o.indirilen)}
      ${bolum("Atlanan (klasörde zaten var)", o.atlanan)}
      ${bolum("Bulunamayan", o.bulunamayan)}
      ${bolum("Geçersiz", o.gecersiz)}
      ${bolum("Hatalı", o.hatali)}
      ${bolum("Birden çok eşleşme", o.coklu)}
      ${bolum("İndirilmedi", o.indirilmedi)}
    </div>
    <div class="alt">
      ${o.bulunamayan.length ? '<button class="btn-sec" id="elogoKopya">Bulunamayanları Kopyala</button>' : ""}
      <button class="btn-primary" id="elogoTamam">Tamam</button>
    </div>`, true);
  p.querySelector("#elogoTamam").onclick = () => p.remove();
  p.querySelector("#elogoTamam").focus();
  const kopya = p.querySelector("#elogoKopya");
  if (kopya) kopya.onclick = () => panoyaYaz(o.bulunamayan.join("\n"), p, kopya);
}

async function panoyaYaz(metin, kapsayici, dugme) {
  try {
    await navigator.clipboard.writeText(metin);
  } catch (_) {
    const t = document.createElement("textarea");
    t.value = metin;
    kapsayici.appendChild(t);
    t.select();
    document.execCommand("copy");
    t.remove();
  }
  dugme.textContent = "Kopyalandı";
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
    const esc = e => { if (e.key === "Escape") kapat(false); };
    const kapat = c => {
      document.removeEventListener("keydown", esc);   // butonla kapatınca da kaldır
      p.remove();
      cevapla(c);
    };
    p.querySelector("#oHayir").onclick = () => kapat(false);
    p.querySelector("#oEvet").onclick = () => kapat(true);
    p.addEventListener("click", e => { if (e.target === p) kapat(false); });
    document.addEventListener("keydown", esc);
    p.querySelector("#oEvet").focus();
  });
}

function bilgiModal(baslik, mesaj) {
  return new Promise(cevapla => {
    const p = modal(`
      <h2>${kacar(baslik)}</h2>
      <div class="aciklama">${kacar(mesaj)}</div>
      <div class="alt"><button class="btn-primary" id="bTamam">Tamam</button></div>`);
    const kapat = () => { p.remove(); cevapla(); };
    p.querySelector("#bTamam").onclick = kapat;   // $() ilk eşleşmeyi bulur, üst üste modalda yanlış olur
    p.addEventListener("click", e => { if (e.target === p) kapat(); });
    p.querySelector("#bTamam").focus();
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
  // Butonlar köprü gidiş-dönüşünden ÖNCE kilitlenmeli: aksi hâlde çift
  // tıklama iki worker başlatıyor, ilk çalışmanın sonucu okunmayan bir
  // kuyrukta kalıyor ve harcanan Gemini kotası boşa gidiyordu.
  $("btnBasla").disabled = true;
  $("btnElogo").disabled = true;
  $("btnRetry").disabled = true;

  const cevap = retry
    ? await pywebview.api.yeniden_dene()
    : await pywebview.api.basla({ klasor: D.klasor, cikti: $("ciktiAd").value,
                                  kalite: D.kalite });
  if (cevap.hata) {
    $("btnBasla").disabled = false;
    $("btnElogo").disabled = false;
    $("btnRetry").disabled = !D.atlanan;
    if (cevap.hata === "api_key") apiKeyModal();
    // bozuk alanlar.json: editöre değil dosyaya yönlendir (bozukken Kaydet reddedilir)
    else if (cevap.sema_hatasi) await bilgiModal("Alanlar okunamadı", cevap.hata);
    else bilgiSatiri(cevap.hata, "err");
    return;
  }

  Object.assign(D, { calisiyor: true, siradaki: 0, toplam: 0, ok: 0, uyarili: 0,
                     atlanan: 0, paralar: {}, uyarilar: [], durduruluyor: false,
                     baslangic: Date.now() });
  D.ucan.clear();
  feedTemizle();
  $("stUcan").hidden = true;
  $("stNe").textContent = "Hazırlanıyor…";
  $("stEta").textContent = "—";
  $("btnDurdur").disabled = false;
  $("btnAlanlar").disabled = true;      // koşu sürerken şema kilitli
  $("btnUyari").disabled = true;
  $("btnExcel").disabled = true;
  durumTazele();
}

async function elogoBaslat() {
  // `basla` gibi: çift tıklama köprü dönmeden kilitlensin.
  const eskiNe = $("stNe").textContent;
  $("btnBasla").disabled = true;
  $("btnElogo").disabled = true;
  $("btnAlanlar").disabled = true;
  $("btnRetry").disabled = true;
  $("btnDurdur").disabled = false;    // Durdur, giriş penceresini de kapatır
  $("stNe").textContent = "eLogo Girişi Bekleniyor…";
  let cevap;
  try {
    cevap = await pywebview.api.elogo_baglan();
  } finally {
    D.durduruluyor = false;
    $("stNe").textContent = eskiNe;
    $("btnBasla").disabled = false;
    $("btnElogo").disabled = false;
    $("btnAlanlar").disabled = false;
    $("btnRetry").disabled = !D.atlanan;
    $("btnDurdur").disabled = true;
  }
  if (cevap.hata) await bilgiModal("eLogo girişi yapılamadı", cevap.hata);
  else if (cevap.ok) numaraEkrani();
}

function numaraEkrani() {
  const p = modal(`
    <h2>eLogo'dan indir</h2>
    <div class="icerik">
      <div class="el-akis">
        <span class="adim bitti"><span class="no">✓</span>eLogo'ya giriş</span><span class="cizgi"></span>
        <span class="adim simdi"><span class="no">2</span>Numaraları yapıştır</span><span class="cizgi"></span>
        <span class="adim"><span class="no">3</span>İndir ve özet</span>
      </div>
      <div class="el-klasor">
        <div class="yol"><small>İnecek klasör</small><span id="elKlasor"></span></div>
        <button class="btn-sec" id="elDegistir">Değiştir</button>
      </div>
      <div class="f mono">
        <label class="el-etiket" for="elNolar">Fatura numaraları</label>
        <div class="el-ipucu">Excel'den kopyalayıp yapıştırabilirsiniz. Alt alta, virgülle ya da boşlukla ayrılmış numaralar da olur.</div>
        <textarea id="elNolar" rows="7" spellcheck="false"
          placeholder="GIB2024000000101&#10;ABC2023000000042"></textarea>
      </div>
      <div class="el-sayac" id="elSayac"></div>
      <div class="el-gecersiz" id="elGecersiz"></div>
    </div>
    <div class="alt">
      <button class="btn-sec" id="elIptal">Vazgeç</button>
      <button class="btn-primary" id="elIndir" disabled>İndir</button>
    </div>`, true);
  p.querySelector(".modal").classList.add("el-modal");
  const q = s => p.querySelector(s);
  const esc = e => { if (e.key === "Escape") kapat(); };
  const kapat = () => { document.removeEventListener("keydown", esc); p.remove(); };
  document.addEventListener("keydown", esc);
  p.addEventListener("click", e => { if (e.target === p) kapat(); });

  let sira = 0, aranacak = 0, zamanlayici;
  const dugme = () => {
    q("#elKlasor").textContent = D.klasor || "Klasör seçilmedi";
    q("#elIndir").disabled = !aranacak || !D.klasor;
    q("#elIndir").textContent = aranacak ? `${aranacak} Faturayı İndir` : "İndir";
  };
  const tazele = async () => {
    const benim = ++sira;
    const o = await pywebview.api.elogo_numara_ozeti(q("#elNolar").value);
    if (benim !== sira) return;           // bu arada yeni yazıldı, eski sonuç gösterilmesin
    aranacak = o.aranacak;
    q("#elSayac").innerHTML =
      (o.aranacak ? `<span class="iyi">${o.aranacak} fatura aranacak</span>`
                  : `<span class="gri">Henüz numara yok</span>`) +
      (o.tekrar ? `<span class="gri">${o.tekrar} tekrar çıkarıldı</span>` : "") +
      (o.gecersiz.length ? `<span class="kotu">${o.gecersiz.length} geçersiz (16 karakterden uzun)</span>` : "");
    q("#elGecersiz").textContent = o.gecersiz.join("  ");
    dugme();
  };
  q("#elNolar").oninput = () => {
    sira++;                               // yoldaki eski yanıt düğmeyi yeniden açmasın
    q("#elIndir").disabled = true;        // sayaç yazılanı yakalayana kadar
    clearTimeout(zamanlayici);
    zamanlayici = setTimeout(tazele, 150);
  };
  q("#elDegistir").onclick = async () => { await klasorSec(); dugme(); };
  q("#elIptal").onclick = kapat;
  q("#elIndir").onclick = () => {
    const metin = q("#elNolar").value;
    clearTimeout(zamanlayici);
    sira++;
    kapat();
    elogoIndir(metin);
  };
  tazele();
  q("#elNolar").focus();
}

async function elogoIndir(metin) {
  $("btnBasla").disabled = true;
  $("btnElogo").disabled = true;
  const cevap = await pywebview.api.elogo_indir(D.klasor, metin);
  if (cevap.hata) {
    $("btnBasla").disabled = false;
    $("btnElogo").disabled = false;
    bilgiSatiri(cevap.hata, "err");
    return;
  }
  Object.assign(D, { calisiyor: true, siradaki: 0, toplam: 0, ok: 0, uyarili: 0,
                     atlanan: 0, paralar: {}, uyarilar: [], durduruluyor: false,
                     baslangic: Date.now() });
  D.ucan.clear();
  feedTemizle();
  $("stUcan").hidden = true;
  $("stNe").textContent = "Hazırlanıyor…";     // oturum dolduysa önce giriş gelir
  $("stEta").textContent = "—";
  $("btnDurdur").disabled = false;
  $("btnAlanlar").disabled = true;
  $("btnRetry").disabled = true;
  $("btnUyari").disabled = true;
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
  $("btnElogo").onclick = elogoBaslat;
  $("btnRetry").onclick = () => basla(true);
  $("btnDurdur").onclick = () => {
    pywebview.api.durdur();
    $("btnDurdur").disabled = true;
    D.durduruluyor = true;      // uçan liste bu mesajın üstüne yazmasın
    $("stNe").textContent = "Durduruluyor — İşlenen Fatura Tamamlanıyor…";
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
  editorKur();
  if (d.klasor) klasorGoster(d.klasor);       // son kullanılan klasör
  if (d.taslak) await taslakSor(d.taslak);
  if (!d.api_key_var) setTimeout(apiKeyModal, 400);
}

/* Yarım kalan inceleme. Karar verilene kadar sorulur: Escape ya da dışarı
   tıklama da "Vazgeç" sayıldığından tek soruda yüzlerce faturanın çıkarımı
   yanlışlıkla silinebilirdi; taslağı tutup yeni koşu başlatmak da onu ezerdi
   (`basla` bu yüzden bekleyen taslakta reddeder). */
async function taslakSor(t) {
  if (t.hata) return bilgiModal("Yarım kalan inceleme okunamadı", t.hata);
  for (;;) {
    if (await onayModal("Yarım kalan inceleme",
          `${t.tarih} tarihinde ${t.sayi} faturalık bir inceleme onaylanmadan kaldı (${t.cikti}). Devam edilsin mi?`,
          "Devam et")) {
      const c = await pywebview.api.taslak_devam();
      if (c.hata) {               // tekrar: Excel okunamadı, düzeltilip yeniden denenebilir
        await bilgiModal("İnceleme açılamadı", c.hata);
        if (c.tekrar) continue;
        return;
      }
      if (c.excel_degisti)
        await bilgiModal("Excel değişmiş",
          `${t.cikti} bu inceleme yarım kaldıktan sonra değişmiş. Mevcut faturalar yeniden okundu; ` +
          "aynı fatura iki kez görünürse mükerrer uyarısına bakın.");
      D.atlanan = c.atlanan;
      return reviewAc(c);
    }
    if (await onayModal("Taslak silinsin mi?",
          "Çıkarılan veriler ve düzeltmeler silinecek, faturalar yeniden işlenmek zorunda kalacak.",
          "Evet, sil", true)) {
      const c = await pywebview.api.taslak_sil();
      return c.hata && bilgiModal("Taslak silinemedi", c.hata);
    }
  }
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
