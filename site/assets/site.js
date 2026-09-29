/* ---- one place to configure the hosted connector ---- */
const REMOTE_URL = "";   // e.g. "https://easa-regs-mcp.onrender.com/mcp" - leave empty until deployed
const REPO = "https://github.com/muchsneaks/easa-regs-mcp";

const LANG = document.documentElement.lang.startsWith("de") ? "de" : "en";
const T = {
  de: { copied: "Kopiert", open: "Menü öffnen", close: "Menü schließen" },
  en: { copied: "Copied", open: "Open menu", close: "Close menu" },
}[LANG];

// language: remember an explicit choice; first-time visitors with a non-German browser get English
document.querySelectorAll("[data-lang]").forEach(a => a.addEventListener("click", () => {
  try { localStorage.setItem("lang", a.dataset.lang); } catch {}
}));

document.documentElement.classList.add("js");
document.getElementById("year").textContent = new Date().getFullYear();

// remote connector wiring
const hasRemote = REMOTE_URL.trim().length > 0;
document.querySelectorAll("[data-needs-remote]").forEach(el => { if (!hasRemote) el.hidden = true; });
document.querySelectorAll("[data-no-remote]").forEach(el => { el.hidden = hasRemote; });
if (hasRemote) {
  document.querySelectorAll("[data-remote-url]").forEach(el => el.textContent = REMOTE_URL);
  document.getElementById("cc-remote").textContent = `claude mcp add --transport http easa-regs ${REMOTE_URL}`;
  document.getElementById("json-remote").textContent = JSON.stringify({ mcpServers: { "easa-regs": { url: REMOTE_URL } } }, null, 2);
  const cfg = btoa(JSON.stringify({ url: REMOTE_URL }));
  document.getElementById("cursor-link").href = `cursor://anysphere.cursor-deeplink/mcp/install?name=easa-regs&config=${encodeURIComponent(cfg)}`;
}

// tabs (keyboard accessible)
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab, focus) {
  tabs.forEach(t => {
    const on = t === tab;
    t.setAttribute("aria-selected", on);
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  });
  if (focus) tab.focus();
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", e => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      selectTab(tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length], true);
    }
  });
});
document.querySelectorAll("[data-goto]").forEach(a => a.addEventListener("click", e => {
  e.preventDefault(); selectTab(document.getElementById(a.dataset.goto), true);
}));
// pick a sensible default: no hosted connector yet -> Desktop; Windows/Mac desktop users see the app tab first otherwise
if (!hasRemote) selectTab(document.getElementById("t-desktop"));

// copy buttons
document.querySelectorAll("[data-copy]").forEach(btn => btn.addEventListener("click", async () => {
  const text = document.querySelector(btn.dataset.copy).textContent.trim();
  const label = btn.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  btn.textContent = T.copied; btn.classList.add("done");
  setTimeout(() => { btn.textContent = label; btn.classList.remove("done"); }, 1800);
}));

// mobile menu
const menu = document.querySelector(".menu"), drawer = document.getElementById("drawer");
menu.addEventListener("click", () => {
  const open = drawer.classList.toggle("open");
  menu.setAttribute("aria-expanded", open);
  menu.setAttribute("aria-label", open ? T.close : T.open);
});
drawer.querySelectorAll("a").forEach(a => a.addEventListener("click", () => { drawer.classList.remove("open"); menu.setAttribute("aria-expanded", false); }));

// scroll reveal
const io = new IntersectionObserver(entries => entries.forEach(e => {
  if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}), { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
document.querySelectorAll(".rv").forEach(el => io.observe(el));
