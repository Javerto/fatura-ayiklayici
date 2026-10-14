"use strict";
/* Alan (şema) editörü. Gözden geçirme ekranıyla aynı desen: gizli tam ekran
   div, tek pencere. Fark: "alandan çıkınca uygula" YOK — yarım yazılmış bir
   alan modele sızmasın, kısıtlar ancak bütün hâlinde denetlenebilir. Her şey
   bellekte düzenlenir, yalnızca Kaydet Python'a gider (orada yeniden denetlenir).

   `anahtar` yalnızca kimliktir; ekranda hiçbir yerde gösterilmez. */

const E = { alanlar: [], secili: 0, degisti: false };
const ED_TIP = { metin: "Metin", tarih: "Tarih", sayi: "Sayı" };

async function editorAc() {
  if (D.calisiyor) {
    await bilgiModal("Alanlar düzenlenemez", "Bir işlem sürerken alanlar değiştirilemez.");
    return;
  }
  const o = await pywebview.api.sema_oku();
  if (o.hata) { await bilgiModal("Alanlar düzenlenemez", o.hata); return; }
  E.alanlar = o.alanlar;
  E.sistem = new Set(o.sistem_basliklar.map(b => b.toLowerCase()));
  E.secili = 0;
  E.degisti = false;
  const h = $("edDosyaHata");
  h.hidden = !o.dosya_hatasi;
  h.textContent = o.dosya_hatasi
    ? `⚠ Alan dosyası okunamadı (${o.dosya_hatasi}). Varsayılan alanlar gösteriliyor; kaydederseniz dosya bunlarla değiştirilir.`
    : "";
  $("anaEkran").hidden = true;
  $("editor").hidden = false;
  document.body.style.overflow = "hidden";
  edListeCiz();
  edSec(0);
}

function edKapat() {
  $("editor").hidden = true;
  $("anaEkran").hidden = false;
  document.body.style.overflow = "";
}

// ═══ DENETİM (Python'daki kuralların aynası; asıl denetim orada) ═══
/** {i: [[tur, mesaj, alan]]} — tur "err" kaydı engeller, "warn" yalnızca uyarır. */
function edDenetle() {
  const sonuc = {}, ekle = (i, t, m, alan) => (sonuc[i] ||= []).push([t, m, alan]);
  const say = {};
  E.alanlar.forEach(a => {
    const k = a.etiket.trim().toLowerCase();
    if (k) say[k] = (say[k] || 0) + 1;
  });
  E.alanlar.forEach((a, i) => {
    const k = a.etiket.trim().toLowerCase();
    if (!k) ekle(i, "err", "Etiket boş olamaz.", "etiket");
    else if (say[k] > 1) ekle(i, "err", "Bu etiket başka bir alanda da kullanılıyor; Excel'de iki aynı başlık olamaz.", "etiket");
    else if (E.sistem.has(k)) ekle(i, "err", "Bu başlık programın kendi sütunlarından birine ait; başka bir etiket seçin.", "etiket");
    if (a.aktif && !a.aciklama.trim())
      ekle(i, "warn", "Açıklama boş — model yalnızca etiketi görecek.", "aciklama");
  });
  return sonuc;
}

function edDurumTazele() {
  const d = edDenetle();
  const hatali = Object.values(d).filter(l => l.some(x => x[0] === "err")).length;
  const uyarili = Object.values(d).filter(l => l.some(x => x[0] === "warn")).length;
  const el = $("edDurum");
  el.className = "ed-durum " + (hatali ? "err" : uyarili ? "warn" : "");
  el.textContent = hatali
    ? `✕ ${hatali} alanda kaydı engelleyen sorun var`
    : uyarili ? `⚠ ${uyarili} alanın açıklaması boş`
    : E.degisti ? "Kaydedilmemiş değişiklik var" : "";
  $("edKaydet").disabled = hatali > 0 || !E.degisti;
  return d;
}

// ═══ LİSTE ═══
function edListeCiz() {
  const d = edDurumTazele();
  $("edSayi").textContent = `${E.alanlar.filter(a => a.aktif).length} etkin alan`;
  $("edListe").innerHTML = E.alanlar.map((a, i) => {
    const l = d[i] || [], err = l.some(x => x[0] === "err"), warn = l.length > 0;
    const etiketler = [ED_TIP[a.tip] || a.tip];
    if (a.cekirdek) etiketler.push("temel");
    if (!a.anahtar) etiketler.push("yeni");
    if (!a.aktif) etiketler.push("pasif");
    return `<div class="rvrow ${warn ? "w" : ""} ${err ? "e" : ""} ${a.aktif ? "" : "ex"} ${
      i === E.secili ? "on" : ""}" data-i="${i}">
      <div class="mk">${err ? "✕" : warn ? "!" : a.aktif ? "✓" : "—"}</div>
      <div class="g">
        <div class="co ed-ad">${kacar(a.etiket.trim() || "(etiketsiz)")}</div>
        <div class="am">${kacar(etiketler.join(" · "))}</div>
      </div></div>`;
  }).join("");
}

// ═══ AYRINTI ═══
/* Form yalnızca seçim değişince ya da yapısal bir işlemde (ekle/kaldır/taşı)
   kurulur — yazarken asla: innerHTML odağı düşürür, Tab sonrası harfleri yer. */
function edSec(i) {
  E.secili = Math.max(0, Math.min(i, E.alanlar.length - 1));
  const a = E.alanlar[E.secili];
  if (!a) { $("edForm").innerHTML = ""; return; }
  const tipKilitli = !!a.anahtar;
  const ogrenKilitli = !edOgrenilebilir(a);
  $("edForm").innerHTML = `
    <div class="f" data-ed="etiket"><span>Etiket (Excel başlığı ve form etiketi)</span>
      <input id="edEtiket" value="${kacar(a.etiket)}" spellcheck="false"></div>
    <div class="f" data-ed="aciklama"><span>Modele açıklama — bu alanda faturadan ne okunmalı?</span>
      <textarea id="edAciklama" rows="5" spellcheck="false">${kacar(a.aciklama)}</textarea></div>
    <div class="f"><span>Tip</span>
      <select id="edTip" ${tipKilitli ? "disabled" : ""}>${Object.entries(ED_TIP).map(([k, v]) =>
        `<option value="${k}" ${a.tip === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <div class="ipucu">${tipKilitli
        ? "Tip yalnızca alan oluşturulurken seçilir. Sonradan değişirse aynı Excel sütununda metin ve sayı karışır."
        : "Kaydettikten sonra tip değiştirilemez."}</div></div>
    <label class="learn"><input type="checkbox" id="edOgrenilir" ${a.ogrenilir ? "checked" : ""} ${
      ogrenKilitli ? "disabled" : ""}>
      <div><div class="t">Firma için hatırla</div>
      <div class="d">${ogrenKilitli
        ? "Yalnızca firmaya göre değişmeyen metin alanlarında (ör. vergi dairesi) açılabilir."
        : "Gözden geçirmede düzelttiğiniz değer bu VKN'ye kaydedilir; aynı firmanın sonraki faturalarında otomatik düzeltilir."}</div></div></label>
    <label class="learn"><input type="checkbox" id="edZorunlu" ${a.zorunlu ? "checked" : ""} ${
      a.cekirdek ? "disabled" : ""}>
      <div><div class="t">Zorunlu</div>
      <div class="d">${a.cekirdek ? "Temel alanların kendi denetim kuralları var."
        : "Boş gelirse gözden geçirmede uyarı verilir."}</div></div></label>
    <div class="ed-alt">${a.cekirdek
      ? `<div class="ipucu">Temel alan: etiketi, açıklaması ve sırası değişebilir; kaldırılamaz.</div>`
      : !a.anahtar
        ? `<button class="btn-sec err" id="edKaldir">Alanı sil</button>
           <div class="ipucu">Henüz kaydedilmedi; silinince iz bırakmaz.</div>`
        : a.aktif
          ? `<button class="btn-sec err" id="edKaldir">Alanı kaldır</button>
             <div class="ipucu">Kaldırılan alan artık okunmaz ve formda görünmez; Excel'deki eski verisi korunur. İstediğiniz zaman geri açabilirsiniz.</div>`
          : `<button class="btn-sec" id="edKaldir">Alanı geri aç</button>
             <div class="ipucu">Bu alan kaldırılmış: okunmuyor, formda görünmüyor. Excel'deki verisi duruyor.</div>`}
      ${RV_GRUP.some(g => g[1].includes(a.anahtar)) ? ""
        : `<div class="ipucu">Gözden geçirme formunda “Diğer” grubunda görünür.</div>`}</div>`;
  $("edYukari").disabled = E.secili === 0;
  $("edAsagi").disabled = E.secili === E.alanlar.length - 1;
  edUyariGoster();
  document.querySelectorAll("#edListe .rvrow").forEach(r =>
    r.classList.toggle("on", +r.dataset.i === E.secili));
}

/** "Firma için hatırla" açılabilir mi — kaydedilmiş alanda Python söyler
    (`sema.ogrenilebilir`), yeni alanda yalnızca metin tipi. */
function edOgrenilebilir(a) {
  return a.anahtar ? a.ogrenilebilir : a.tip === "metin";
}

/** Seçili alanın mesajlarını yerinde günceller — formu yeniden kurmadan. */
function edUyariGoster() {
  const l = edDenetle()[E.secili] || [];
  $("edForm").querySelectorAll(".f[data-ed]").forEach(f => {
    const benim = l.filter(x => x[2] === f.dataset.ed);
    f.classList.toggle("bad", benim.some(x => x[0] === "warn"));
    f.classList.toggle("hata", benim.some(x => x[0] === "err"));
    f.querySelectorAll(".msg").forEach(e => e.remove());
    for (const [t, m] of benim)
      f.insertAdjacentHTML("beforeend",
        `<div class="msg ${t}"><span>${t === "err" ? "✕" : "⚠"}</span><span>${kacar(m)}</span></div>`);
  });
}

function edDegisti() {
  E.degisti = true;
  edListeCiz();
  edUyariGoster();
}

function edTasi(yon) {
  const i = E.secili, j = i + yon;
  if (j < 0 || j >= E.alanlar.length) return;
  [E.alanlar[i], E.alanlar[j]] = [E.alanlar[j], E.alanlar[i]];
  E.secili = j;
  edDegisti();
  edSec(j);
}

function edEkle() {
  const kullanilan = new Set(E.alanlar.map(a => a.etiket.trim().toLowerCase()));
  let etiket = "Yeni alan", n = 2;
  while (kullanilan.has(etiket.toLowerCase())) etiket = `Yeni alan ${n++}`;
  E.alanlar.push({ etiket, tip: "metin", aciklama: "", aktif: true,
                   zorunlu: false, ogrenilir: false, cekirdek: false });
  edDegisti();
  edSec(E.alanlar.length - 1);
  $("edEtiket").select();
  $("edEtiket").focus();
}

function edKaldir() {
  const a = E.alanlar[E.secili];
  if (!a || a.cekirdek) return;
  if (!a.anahtar) E.alanlar.splice(E.secili, 1);   // hiç kaydedilmemiş: iz bırakmaz
  else a.aktif = !a.aktif;                         // kaydedilmiş: pasif/etkin
  edDegisti();
  edSec(E.secili);
}

// ═══ KAYDET / VAZGEÇ ═══
async function edKaydet() {
  const d = edDenetle();
  const hatalar = Object.entries(d).filter(([, l]) => l.some(x => x[0] === "err"));
  if (hatalar.length) {
    edSec(+hatalar[0][0]);
    await bilgiModal("Kaydedilemez", hatalar.map(([i, l]) =>
      `${E.alanlar[i].etiket.trim() || "(etiketsiz)"}: ${l.filter(x => x[0] === "err").map(x => x[1]).join(" ")}`).join("\n"));
    return;
  }
  const bos = E.alanlar.filter((a, i) => (d[i] || []).length);
  if (bos.length && !await onayModal("Açıklaması boş alanlar",
      `${bos.map(a => a.etiket.trim()).join(", ")} için açıklama yok; model yalnızca etiketi görecek. Yine de kaydedilsin mi?`,
      "Yine de kaydet")) return;

  $("edKaydet").disabled = true;
  const c = await pywebview.api.sema_kaydet(E.alanlar.map(a => ({
    anahtar: a.anahtar, etiket: a.etiket.trim(), tip: a.tip,
    aciklama: a.aciklama.trim(), aktif: a.aktif, zorunlu: a.zorunlu,
    ogrenilir: a.ogrenilir })));
  if (c.hata) {                         // ekran açık kalır, düzenlemeler kaybolmaz
    edDurumTazele();
    await bilgiModal("Alanlar kaydedilemedi", c.hata);
    return;
  }
  E.degisti = false;
  edKapat();
  bilgiSatiri("Alanlar kaydedildi — bir sonraki işlemde geçerli olacak.");
}

async function edVazgec() {
  if (E.degisti && !await onayModal("Kaydedilmemiş değişiklikler",
      "Yaptığınız değişiklikler kaydedilmeyecek. Emin misiniz?",
      "Değişiklikleri at", true)) return;
  edKapat();
}

// ═══ DENE ═══
/* Tek faturayı KAYITLI alanlarla okur (Python `dene`); Excel'e ve geçmişe
   yazmaz. Ekrandaki kaydedilmemiş hâl denenmez: denenen şema, sonraki
   koşunun kullanacağı şemayla aynı olmalı. */
async function edDene() {
  if (E.degisti && !await onayModal("Kaydedilmemiş değişiklikler",
      "Deneme kayıtlı alanlarla yapılır; ekrandaki kaydedilmemiş değişiklikler denemeye katılmaz.\n" +
      "Yeni hâlini denemek için önce Kaydet'e basıp Alanlar'ı yeniden açın.",
      "Kayıtlı hâliyle dene")) return;
  const yol = await pywebview.api.dene_sec();
  if (!yol) return;
  const ad = yol.split(/[\\/]/).pop();
  $("edDene").disabled = true;
  const bekle = modal(`
    <h2>Deneniyor…</h2>
    <div class="aciklama">${kacar(ad)} kayıtlı alanlarla okunuyor. Bu birkaç saniye, sunucu yoğunsa birkaç dakika sürebilir. Excel'e hiçbir şey yazılmaz.</div>
    <div class="alt"><button class="btn-sec" id="dDurdur">Durdur</button></div>`);
  bekle.querySelector("#dDurdur").onclick = () => pywebview.api.durdur();
  let o;
  try {
    o = await pywebview.api.dene(yol);
  } finally {
    bekle.remove();
    $("edDene").disabled = false;
  }
  if (o.hata === "api_key") { apiKeyModal(); return; }
  if (o.hata) { await bilgiModal("Deneme yapılamadı", o.hata); return; }

  const uyari = {};
  for (const [alan, mesaj] of o.uyarilar) (uyari[alan] ||= []).push(mesaj);
  modal(`
    <h2>Deneme sonucu</h2>
    <div class="aciklama">${kacar(ad)} · ${kacar(o.kaynak || "")} · Excel'e hiçbir şey yazılmadı.
Yanlış okunan alanın açıklamasını düzeltip kaydedin, sonra yeniden deneyin.</div>
    <div class="icerik"><table><thead><tr><th>Alan</th><th>Okunan değer</th></tr></thead><tbody>
      ${o.alanlar.map(([anahtar, etiket, deger]) => `<tr>
        <td>${kacar(etiket)}</td>
        <td>${deger ? kacar(deger) : '<span class="ipucu">(boş)</span>'}
          ${(uyari[anahtar] || []).map(m => `<div class="ed-uyari">⚠ ${kacar(m)}</div>`).join("")}</td>
      </tr>`).join("")}
    </tbody></table></div>
    <div class="alt"><button class="btn-primary" onclick="this.closest('.perde').remove()">Kapat</button></div>
  `, true);
}

// ═══ BAĞLAMA ═══
function editorKur() {
  $("btnAlanlar").onclick = editorAc;
  $("edListe").onclick = e => {
    const r = e.target.closest(".rvrow");
    if (r) edSec(+r.dataset.i);
  };
  $("edForm").addEventListener("input", e => {
    const a = E.alanlar[E.secili];
    if (!a) return;
    if (e.target.id === "edEtiket") a.etiket = e.target.value;
    else if (e.target.id === "edAciklama") a.aciklama = e.target.value;
    else return;
    edDegisti();
  });
  $("edForm").addEventListener("change", e => {
    const a = E.alanlar[E.secili];
    if (!a) return;
    if (e.target.id === "edTip" && !a.anahtar) {
      a.tip = e.target.value;
      if (!edOgrenilebilir(a)) a.ogrenilir = false;
      edDegisti();
      edSec(E.secili);                  // kutunun kilidi tipe bağlı
      return;
    }
    else if (e.target.id === "edOgrenilir" && edOgrenilebilir(a)) a.ogrenilir = e.target.checked;
    else if (e.target.id === "edZorunlu" && !a.cekirdek) a.zorunlu = e.target.checked;
    else return;
    edDegisti();
  });
  $("edForm").addEventListener("click", e => {
    if (e.target.id === "edKaldir") edKaldir();
  });
  $("edEkle").onclick = edEkle;
  $("edYukari").onclick = () => edTasi(-1);
  $("edAsagi").onclick = () => edTasi(1);
  $("edKaydet").onclick = edKaydet;
  $("edDene").onclick = edDene;
  $("edKapat").onclick = edVazgec;
}
