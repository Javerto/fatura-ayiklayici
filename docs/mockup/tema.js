// Tema seçici — mockup için. Gerçek uygulamada seçim .env'e yazılır.
const TEMALAR = [
  ["mocha",     "Mocha",     "koyu",        "#1e1e2e", "#89b4fa"],
  ["macchiato", "Macchiato", "koyu yumuşak","#24273a", "#8aadf4"],
  ["frappe",    "Frappé",    "koyu ılık",   "#303446", "#8caaee"],
  ["nord",      "Nord",      "koyu mavi",   "#2e3440", "#88c0d0"],
  ["latte",     "Latte",     "açık",        "#ffffff", "#1e66f5"],
  ["kagit",     "Kağıt",     "açık sıcak",  "#fdf9ee", "#268bd2"],
];

function temaKur(btnId, wrapId) {
  const wrap = document.getElementById(wrapId);
  const menu = document.createElement("div");
  menu.className = "tema-menu";
  menu.innerHTML = '<div class="bas">Tema</div>' + TEMALAR.map(
    ([id, ad, not, bg, ac]) => `
      <button class="tema-opt" data-t="${id}">
        <span class="sw" style="background:linear-gradient(135deg,${bg} 55%,${ac} 55%)"></span>
        <span>${ad}<span style="color:var(--dim);font-size:11px"> · ${not}</span></span>
        <span class="tik"></span>
      </button>`).join("");
  wrap.appendChild(menu);

  const isaretle = () => {
    const su = document.documentElement.dataset.tema;
    menu.querySelectorAll(".tema-opt").forEach(o => {
      const secili = o.dataset.t === su;
      o.classList.toggle("on", secili);
      o.querySelector(".tik").textContent = secili ? "✓" : "";
    });
  };

  document.getElementById(btnId).onclick = e => {
    e.stopPropagation();
    menu.classList.toggle("acik");
    isaretle();
  };
  menu.onclick = e => {
    const o = e.target.closest(".tema-opt");
    if (!o) return;
    document.documentElement.dataset.tema = o.dataset.t;
    localStorage.setItem("tema", o.dataset.t);
    isaretle();
  };
  document.addEventListener("click", () => menu.classList.remove("acik"));

  document.documentElement.dataset.tema = localStorage.getItem("tema") || "mocha";
}
