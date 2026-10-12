// DeepShield content script. Shows a small "Scan" chip on hover over media and a
// result panel after the user clicks it. It never scans or sends anything on its own.
(() => {
  if (window.__deepshield) return;
  window.__deepshield = true;

  const MIN_SIZE = 120;
  let settings = { hoverChips: true };
  chrome.runtime.sendMessage({ type: "settings" }, (r) => {
    if (r?.ok) settings = r.result;
  });

  const host = document.createElement("deepshield-ui");
  host.style.cssText = "position:absolute;top:0;left:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
      .chip { position: fixed; display: none; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px;
        background: #0e1524; color: #e6edf7; border: 1px solid #22d3ee; font-size: 12px; font-weight: 600; cursor: pointer;
        box-shadow: 0 4px 14px rgba(0,0,0,.35); }
      .chip:focus-visible { outline: 2px solid #67e8f9; outline-offset: 2px; }
      .panel { position: fixed; width: 340px; max-width: calc(100vw - 24px); background: #0e1524; color: #e6edf7; border: 1px solid #22304a;
        border-radius: 14px; padding: 14px; font-size: 13px; line-height: 1.45; box-shadow: 0 12px 40px rgba(0,0,0,.45); display: none; }
      .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
      .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-weight: 600; font-size: 12px; border: 1px solid; }
      .likely_authentic { color: #4ade80; border-color: #4ade8055; background: #4ade8014; }
      .uncertain { color: #a3b1c6; border-color: #a3b1c655; background: #a3b1c614; }
      .potentially_manipulated { color: #fbbf24; border-color: #fbbf2455; background: #fbbf2414; }
      .high_risk { color: #f87171; border-color: #f8717155; background: #f8717114; }
      .muted { color: #93a3bb; font-size: 12px; }
      button { font: inherit; cursor: pointer; }
      .x { background: none; border: 0; color: #93a3bb; font-size: 18px; line-height: 1; padding: 2px 6px; }
      .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
      .btn { border: 1px solid #22304a; background: #141e31; color: #e6edf7; border-radius: 8px; padding: 6px 10px; font-size: 12px; text-decoration: none; }
      .btn.primary { background: #22d3ee; color: #04212a; border-color: #22d3ee; font-weight: 600; }
      .spin { width: 14px; height: 14px; border: 2px solid #22d3ee55; border-top-color: #22d3ee; border-radius: 50%; animation: s 0.8s linear infinite; display: inline-block; }
      @keyframes s { to { transform: rotate(360deg); } }
      .warn { position: fixed; display: none; padding: 6px 10px; border-radius: 8px; background: #7f1d1dEE; color: #fff; font-size: 12px;
        font-weight: 600; border: 1px solid #f87171; cursor: pointer; max-width: 260px; }
    </style>
    <button class="chip" aria-label="Scan this media with DeepShield">🛡 Scan</button>
    <div class="panel" role="dialog" aria-label="DeepShield result"></div>
    <button class="warn" aria-label="DeepShield warning. Click for details."></button>`;
  const chip = root.querySelector(".chip");
  const panel = root.querySelector(".panel");
  const warn = root.querySelector(".warn");
  document.documentElement.appendChild(host);

  let target = null;
  let hideTimer = null;
  let lastResult = null;

  const mediaUrl = (el) => {
    if (el.tagName === "IMG") return el.currentSrc || el.src;
    if (el.tagName === "VIDEO" || el.tagName === "AUDIO") return el.currentSrc || el.src || el.querySelector("source")?.src || "";
    return "";
  };

  const placeChip = (el) => {
    const r = el.getBoundingClientRect();
    chip.style.left = `${Math.max(4, r.right - 84)}px`;
    chip.style.top = `${Math.max(4, r.top + 8)}px`;
    chip.style.display = "inline-flex";
  };

  document.addEventListener(
    "mouseover",
    (e) => {
      if (!settings.hoverChips) return;
      const el = e.target;
      if (!(el instanceof HTMLElement) || !["IMG", "VIDEO"].includes(el.tagName)) return;
      const r = el.getBoundingClientRect();
      if (r.width < MIN_SIZE || r.height < MIN_SIZE || !mediaUrl(el)) return;
      clearTimeout(hideTimer);
      target = el;
      placeChip(el);
    },
    { passive: true },
  );
  document.addEventListener(
    "mouseout",
    (e) => {
      if (e.target === target) hideTimer = setTimeout(() => (chip.style.display = "none"), 600);
    },
    { passive: true },
  );
  chip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  window.addEventListener("scroll", () => (chip.style.display = "none"), { passive: true });

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const showPanel = (anchor, html) => {
    panel.innerHTML = html;
    const r = anchor?.getBoundingClientRect?.() ?? { left: window.innerWidth - 360, bottom: 20 };
    panel.style.left = `${Math.min(Math.max(12, r.left), window.innerWidth - 352)}px`;
    panel.style.top = `${Math.min(Math.max(12, (r.bottom ?? 20) + 8), window.innerHeight - 260)}px`;
    panel.style.display = "block";
    panel.querySelector(".x")?.addEventListener("click", () => (panel.style.display = "none"));
  };

  const header = `<div class="row"><strong>DeepShield AI</strong><button class="x" aria-label="Close">×</button></div>`;

  async function toB64(url) {
    const blob = await (await fetch(url)).blob();
    if (blob.size > 50 * 1024 * 1024) throw new Error("Embedded media is larger than 50 MB");
    const buf = new Uint8Array(await blob.arrayBuffer());
    let s = "";
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return { dataB64: btoa(s), mime: blob.type };
  }

  async function scan(el, url, isPage = false) {
    chip.style.display = "none";
    showPanel(el, `${header}<p><span class="spin"></span> Analyzing ${isPage ? "this page" : "media"}… this can take a moment.</p>`);
    try {
      const msg = { type: "scan", url, pageUrl: location.href };
      if (/^(blob|data):/.test(url)) Object.assign(msg, await toB64(url), { url: undefined, name: "page-media" });
      const r = await chrome.runtime.sendMessage(msg);
      if (!r?.ok) throw new Error(r?.error || "Scan failed");
      render(el, r.result);
    } catch (e) {
      showPanel(el, `${header}<p>${esc(e.message)}</p><p class="muted">Tip: some platforms only expose media to signed-in users. Download the file you're allowed to analyze and upload it in the dashboard.</p>`);
    }
  }

  function render(el, res) {
    lastResult = res;
    const cls = res.classification;
    const body =
      res.status === "failed"
        ? `<p>Couldn't analyze: ${esc(res.error)}</p>`
        : `<p><span class="badge ${esc(cls)}">${esc(res.label)}</span></p>
           <p>${esc(res.summary)}</p>
           <p class="muted">Reliability: ${esc(res.reliability)} · Synthetic origin: ${esc((res.synthetic || "unknown").replace("_", " "))}</p>
           <p class="muted">An automated estimate, not proof. AI-generated isn't the same as malicious.</p>`;
    showPanel(
      el,
      `${header}${body}<div class="actions">
         <a class="btn primary" href="${esc(res.reportUrl)}" target="_blank" rel="noopener">Full report</a>
         ${res.status === "completed" ? `<button class="btn" data-act="report">Flag for review</button>` : ""}
       </div>`,
    );
    panel.querySelector('[data-act="report"]')?.addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      const r = await chrome.runtime.sendMessage({ type: "report", analysisId: res.id, pageUrl: location.href });
      ev.target.textContent = r?.ok ? "Saved to Investigations ✓" : "Couldn't save";
    });
    if (res.warn && el instanceof HTMLElement) {
      const r = el.getBoundingClientRect();
      warn.textContent = `⚠ DeepShield: ${res.label}. Click for details.`;
      warn.style.left = `${Math.max(4, r.left + 8)}px`;
      warn.style.top = `${Math.max(4, r.top + 8)}px`;
      warn.style.display = "block";
    }
  }

  warn.addEventListener("click", () => {
    warn.style.display = "none";
    if (lastResult) render(null, lastResult);
  });

  chip.addEventListener("click", () => target && scan(target, mediaUrl(target)));

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type !== "ds-context-scan") return;
    const el = msg.page ? null : [...document.querySelectorAll("img,video,audio")].find((m) => mediaUrl(m) === msg.url) || null;
    scan(el, msg.url, msg.page);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") panel.style.display = "none";
  });
})();
