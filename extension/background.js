// DeepShield service worker: talks to the DeepShield API on behalf of the content
// script and popup. Nothing is scanned unless the user clicks a scan control.
import { LABELS, RANK, getSettings } from "./shared.js";

const POLL_MS = 1500;
const MAX_WAIT_MS = 180000;

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "ds-scan-media", title: "Scan with DeepShield", contexts: ["image", "video", "audio"] });
  chrome.contextMenus.create({ id: "ds-scan-page", title: "Check this page for impersonation", contexts: ["page"] });
});

async function call(path, init = {}) {
  const s = await getSettings();
  if (!s.token) throw new Error("Add your DeepShield API token in the extension options first.");
  const headers = { Authorization: `Bearer ${s.token}`, ...(init.headers || {}) };
  let res;
  try {
    res = await fetch(`${s.apiBase.replace(/\/$/, "")}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new Error("Can't reach the DeepShield API. Check the API address in options.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* ignore */
    }
    if (res.status === 401) detail = "Your API token is invalid or revoked. Update it in options.";
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

async function waitFor(id) {
  const start = Date.now();
  while (Date.now() - start < MAX_WAIT_MS) {
    const a = await call(`/analyses/${id}`);
    if (a.status === "completed" || a.status === "failed") return a;
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
  throw new Error("The analysis is taking longer than expected. Check the DeepShield dashboard.");
}

function b64ToBlob(b64, type) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type });
}

async function remember(a) {
  const s = await getSettings();
  if (!s.keepHistory) return;
  const { history = [] } = await chrome.storage.local.get("history");
  history.unshift({ id: a.id, classification: a.classification, url: a.source_url, at: Date.now(), status: a.status });
  await chrome.storage.local.set({ history: history.slice(0, 20) });
}

function brief(a, s) {
  const r = a.result || {};
  const asmt = r.assessment || {};
  return {
    id: a.id,
    status: a.status,
    error: a.error,
    classification: a.classification,
    label: LABELS[a.classification] || a.status,
    summary: asmt.summary || a.error || "",
    synthetic: asmt.synthetic_origin,
    reliability: asmt.reliability,
    warn: a.classification ? RANK[a.classification] >= RANK[s.warnLevel] : false,
    reportUrl: `${s.appBase.replace(/\/$/, "")}/analyses/${a.id}`,
    embedded: (r.embedded_media || []).map((m) => m.analysis_id),
  };
}

export async function scan({ url, pageUrl, dataB64, mime, name }) {
  const s = await getSettings();
  let created;
  if (dataB64) {
    const fd = new FormData();
    fd.append("file", b64ToBlob(dataB64, mime || "application/octet-stream"), name || "page-media");
    created = await call("/analyses/upload", { method: "POST", body: fd });
  } else {
    created = await call("/analyses/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, page_url: pageUrl, source: "extension" }),
    });
  }
  const done = await waitFor(created.id);
  await remember(done);
  const out = brief(done, s);
  if (out.warn) {
    chrome.notifications.create(`ds-${done.id}`, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: `DeepShield: ${out.label}`,
      message: (out.summary || "").slice(0, 200),
      priority: 1,
    });
  }
  return out;
}

async function reportForReview({ analysisId, pageUrl }) {
  let host = "page";
  try {
    host = new URL(pageUrl).hostname;
  } catch {
    /* ignore */
  }
  return call("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: `Flagged from browser: ${host}`.slice(0, 200), analysis_id: analysisId }),
  });
}

chrome.notifications.onClicked.addListener(async (nid) => {
  if (!nid.startsWith("ds-")) return;
  const s = await getSettings();
  chrome.tabs.create({ url: `${s.appBase.replace(/\/$/, "")}/analyses/${nid.slice(3)}` });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id) return;
  const url = info.menuItemId === "ds-scan-page" ? info.pageUrl : info.srcUrl;
  chrome.tabs.sendMessage(tab.id, { type: "ds-context-scan", url, pageUrl: info.pageUrl, page: info.menuItemId === "ds-scan-page" });
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    try {
      if (msg.type === "scan") reply({ ok: true, result: await scan(msg) });
      else if (msg.type === "report") reply({ ok: true, result: await reportForReview(msg) });
      else if (msg.type === "settings") reply({ ok: true, result: { hoverChips: (await getSettings()).hoverChips } }); // never expose the token to page context
      else if (msg.type === "ping") reply({ ok: true, result: await call("/auth/me") });
      else reply({ ok: false, error: "Unknown request" });
    } catch (e) {
      reply({ ok: false, error: e.message || String(e) });
    }
  })();
  return true;
});
