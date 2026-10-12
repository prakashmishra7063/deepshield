// Thin API client. The access token lives in sessionStorage (cleared when the tab closes).
// All requests go through the same-origin /api proxy configured in next.config.ts.

export type Classification = "likely_authentic" | "uncertain" | "potentially_manipulated" | "high_risk";

export interface User {
  id: number;
  email: string;
  role: string;
  alert_threshold: string;
  email_alerts: boolean;
  created_at: string;
}

export interface Signal {
  detector: string;
  id: string;
  title: string;
  strength: "weak" | "moderate" | "strong";
  direction: "manipulated" | "synthetic" | "authentic" | "neutral";
  detail: string;
  category: string | null;
  evidence: Record<string, unknown>;
  timestamp_s: number | null;
}

export interface DetectorSummary {
  name: string;
  version: string;
  status: "ok" | "unavailable" | "error" | "skipped";
  reason: string | null;
  calibrated: boolean;
  score: number | null;
}

export interface EvidenceItem {
  name: string;
  kind: "heatmap" | "frame" | "spectrogram";
  caption: string;
  timestamp_s: number | null;
}

export interface AnalysisResult {
  pipeline_version: string;
  assessment: {
    classification: Classification;
    label: string;
    summary: string;
    likelihood: number | null;
    likelihood_calibrated: boolean;
    reliability: "low" | "medium" | "high";
    synthetic_origin: "declared" | "suspected" | "none_detected" | "unknown";
    categories: string[];
  };
  signals: Signal[];
  detectors: DetectorSummary[];
  evidence: EvidenceItem[];
  facts: Record<string, Record<string, unknown>>;
  limitations: string[];
  next_steps: string[];
  media: { kind: string; mime: string; sha256: string; size: number; name: string | null; source_url: string | null };
  platform?: { id: string; name: string; status: string; detail: string };
  embedded_media?: { analysis_id: string; url: string; kind: string }[];
}

export interface AnalysisSummary {
  id: string;
  source_type: string;
  source_url: string | null;
  page_url: string | null;
  kind: string | null;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  stage: string;
  classification: Classification | null;
  synthetic_origin: string | null;
  likelihood: number | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  file_name: string | null;
}

export interface Analysis extends AnalysisSummary {
  result: AnalysisResult | null;
  media_available: boolean;
}

export interface CaseSummary {
  id: number;
  title: string;
  status: "open" | "reported" | "resolved" | "dismissed";
  created_at: string;
  updated_at: string;
  item_count: number;
}

export interface CaseDetail extends CaseSummary {
  items: AnalysisSummary[];
  notes: { id: number; body: string; user_id: number; created_at: string }[];
}

export interface AlertItem {
  id: number;
  analysis_id: string | null;
  level: Classification;
  title: string;
  state: "new" | "acknowledged" | "dismissed";
  created_at: string;
}

export interface ApiToken {
  id: number;
  name: string;
  prefix: string;
  revoked: boolean;
  last_used_at: string | null;
  created_at: string;
  token?: string;
}

const TOKEN_KEY = "ds_token";

export const auth = {
  get(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(t: string) {
    try {
      sessionStorage.setItem(TOKEN_KEY, t);
    } catch {
      /* storage unavailable */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage unavailable */
    }
  },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { msg?: string; loc?: unknown[] };
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "";
      return `${field ? `${String(field)}: ` : ""}${first.msg ?? "Invalid input"}`;
    }
  }
  if (status === 429) return "Too many requests. Please wait a moment.";
  return `Request failed (${status})`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = auth.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`/api/v1${path}`, { ...init, headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    auth.clear();
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
  }
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detailMessage(parsed, res.status));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function evidenceUrl(analysisId: string, name: string): Promise<string> {
  const res = await fetch(`/api/v1/analyses/${analysisId}/evidence/${encodeURIComponent(name)}`, {
    headers: { Authorization: `Bearer ${auth.get() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(res.status, "Evidence unavailable");
  return URL.createObjectURL(await res.blob());
}

export function uploadFile(file: File, onProgress: (pct: number) => void): Promise<Analysis> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/analyses/upload");
    const token = auth.get();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Analysis);
      else reject(new ApiError(xhr.status, detailMessage(body, xhr.status)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}
