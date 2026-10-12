import type { Classification } from "./api";

export const CLASS_META: Record<Classification, { label: string; short: string; tone: string; explain: string }> = {
  likely_authentic: {
    label: "Likely Authentic",
    short: "Authentic",
    tone: "ok",
    explain: "No strong manipulation indicators were detected, and the available evidence supports authenticity.",
  },
  uncertain: {
    label: "Uncertain",
    short: "Uncertain",
    tone: "unc",
    explain: "Evidence is insufficient or conflicting. That is not a clean bill of health.",
  },
  potentially_manipulated: {
    label: "Potentially Manipulated",
    short: "Potential",
    tone: "warn",
    explain: "One or more meaningful indicators of editing or manipulation were detected.",
  },
  high_risk: {
    label: "High Risk — Possible Deepfake",
    short: "High risk",
    tone: "danger",
    explain: "Multiple independent signals indicate a substantial possibility of manipulation.",
  },
};

export const SYNTHETIC_LABEL: Record<string, string> = {
  declared: "AI generation declared",
  suspected: "AI generation suspected",
  none_detected: "No AI-generation indicators",
  unknown: "Synthetic origin unknown",
};

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export function sourceLabel(a: { source_url: string | null; file_name: string | null; id: string }): string {
  if (a.file_name) return a.file_name;
  if (a.source_url) {
    try {
      const u = new URL(a.source_url);
      return u.hostname + (u.pathname.length > 1 ? u.pathname : "");
    } catch {
      return a.source_url;
    }
  }
  return a.id;
}

export function prettify(s: string): string {
  return s.replace(/_/g, " ");
}
