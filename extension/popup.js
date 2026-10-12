import { LABELS, getSettings } from "./shared.js";

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, text = "") {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  if (text) e.textContent = text;
  return e;
}

async function renderHistory() {
  const s = await getSettings();
  const { history = [] } = await chrome.storage.local.get("history");
  const ul = $("history");
  ul.replaceChildren();
  if (!history.length) ul.append(el("li", { class: "muted" }, "No scans yet."));
  for (const h of history.slice(0, 8)) {
    const li = el("li");
    const a = el("a", { href: `${s.appBase.replace(/\/$/, "")}/analyses/${h.id}`, target: "_blank" }, h.id);
    li.append(a, el("span", { class: `badge ${h.classification || ""}` }, LABELS[h.classification] || h.status));
    ul.append(li);
  }
}

async function init() {
  const r = await chrome.runtime.sendMessage({ type: "ping" });
  if (r?.ok) {
    $("status").textContent = `Connected as ${r.result.email}`;
    $("scan-page").disabled = false;
  } else {
    $("status").textContent = r?.error || "Not connected";
  }
  renderHistory();
}

$("scan-page").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url?.startsWith("http")) {
    $("result").textContent = "Only http(s) pages can be checked.";
    return;
  }
  $("scan-page").disabled = true;
  $("result").textContent = "Analyzing this page…";
  const r = await chrome.runtime.sendMessage({ type: "scan", url: tab.url, pageUrl: tab.url });
  $("scan-page").disabled = false;
  const box = $("result");
  box.replaceChildren();
  if (!r?.ok) {
    box.textContent = r?.error || "Scan failed";
    return;
  }
  box.append(el("p", { class: `badge ${r.result.classification || ""}` }, r.result.label), el("p", {}, r.result.summary));
  const s = await getSettings();
  box.append(el("a", { href: `${s.appBase.replace(/\/$/, "")}/analyses/${r.result.id}`, target: "_blank" }, "Open full report"));
  renderHistory();
});

$("clear").addEventListener("click", async () => {
  await chrome.storage.local.set({ history: [] });
  renderHistory();
});

init();
