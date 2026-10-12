import { DEFAULTS, getSettings } from "./shared.js";

const $ = (id) => document.getElementById(id);
const fields = Object.keys(DEFAULTS);

(async () => {
  const s = await getSettings();
  for (const k of fields) {
    const e = $(k);
    if (!e) continue;
    if (e.type === "checkbox") e.checked = !!s[k];
    else e.value = s[k] ?? "";
  }
})();

$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const next = {};
  for (const k of fields) {
    const e = $(k);
    if (!e) continue;
    next[k] = e.type === "checkbox" ? e.checked : e.value.trim();
  }
  try {
    const origin = new URL(next.apiBase).origin + "/*";
    const local = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/\*$/.test(origin);
    if (!local) {
      const granted = await chrome.permissions.request({ origins: [origin] });
      if (!granted) {
        $("msg").textContent = "Permission to reach the API address was declined.";
        return;
      }
    }
  } catch {
    $("msg").textContent = "Enter a valid API address.";
    return;
  }
  await chrome.storage.local.set(next);
  const r = await chrome.runtime.sendMessage({ type: "ping" });
  $("msg").textContent = r?.ok ? `Saved. Connected as ${r.result.email}.` : `Saved, but: ${r?.error}`;
});
