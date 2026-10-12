// Shared settings helpers (used by background, popup and options).
export const DEFAULTS = {
  apiBase: "http://localhost:8000",
  appBase: "http://localhost:3100",
  token: "",
  warnLevel: "high_risk", // "high_risk" | "potentially_manipulated"
  hoverChips: true,
  keepHistory: true,
};

export async function getSettings() {
  const s = await chrome.storage.local.get(Object.keys(DEFAULTS));
  return { ...DEFAULTS, ...s };
}

export const LABELS = {
  likely_authentic: "Likely Authentic",
  uncertain: "Uncertain",
  potentially_manipulated: "Potentially Manipulated",
  high_risk: "High Risk — Possible Deepfake",
};

export const RANK = { likely_authentic: 0, uncertain: 1, potentially_manipulated: 2, high_risk: 3 };
