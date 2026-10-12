"use client";

import { ArrowLeft, Download, ExternalLink, FileJson, FolderPlus, Info, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EvidenceImage, VideoTimeline } from "@/components/Evidence";
import { Button, Card, ClassBadge, ErrorNote, Pill, Progress, Spinner, StatusPill, cx, inputCls } from "@/components/ui";
import { api, type Analysis, type CaseSummary, type Signal } from "@/lib/api";
import { SYNTHETIC_LABEL, fmtBytes, fmtDate, prettify, sourceLabel } from "@/lib/format";

const DIR_TONE: Record<Signal["direction"], string> = { manipulated: "warn", synthetic: "accent", authentic: "ok", neutral: "unc" };
const DIR_LABEL: Record<Signal["direction"], string> = {
  manipulated: "manipulation",
  synthetic: "AI origin",
  authentic: "authenticity",
  neutral: "context",
};

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [a, setA] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);

  const load = useCallback(() => api<Analysis>(`/analyses/${id}`).then(setA).catch((e) => setError(e.message)), [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!a || a.status === "completed" || a.status === "failed") return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [a, load]);

  const exportReport = async (format: "pdf" | "json") => {
    try {
      const r = await api<{ url: string }>(`/analyses/${id}/report-link`, { method: "POST", json: { format } });
      window.location.href = r.url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    }
  };

  const remove = async () => {
    if (!confirm("Delete this analysis, its evidence and the stored original? This cannot be undone.")) return;
    try {
      await api(`/analyses/${id}`, { method: "DELETE" });
      router.replace("/history");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  if (!a) return error ? <ErrorNote message={error} /> : <Spinner />;
  const r = a.result;
  const shown = r ? r.signals.filter((s) => advanced || s.direction !== "neutral" || s.strength !== "weak") : [];
  const done = a.status === "completed" || a.status === "failed";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/history" className="mb-2 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
            <ArrowLeft className="h-4 w-4" aria-hidden /> History
          </Link>
          <h1 className="truncate text-2xl font-semibold tracking-tight" title={sourceLabel(a)}>
            {sourceLabel(a)}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span className="font-mono">{a.id}</span>·<span>{fmtDate(a.created_at)}</span>·<Pill>{a.kind ?? "detecting type"}</Pill>
            <Pill>{a.source_type}</Pill>
            <StatusPill status={a.status} />
          </p>
        </div>
        {done && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => exportReport("pdf")}>
              <Download className="h-4 w-4" aria-hidden /> PDF report
            </Button>
            <Button variant="secondary" onClick={() => exportReport("json")}>
              <FileJson className="h-4 w-4" aria-hidden /> JSON
            </Button>
            <AddToCase analysisId={a.id} />
            <Button variant="danger" onClick={remove} aria-label="Delete analysis">
              <Trash2 className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        )}
      </div>
      <ErrorNote message={error} />

      {!done && (
        <Card>
          <p className="mb-3 text-sm font-medium" aria-live="polite">
            {a.stage}… <span className="text-muted">{a.progress}%</span>
          </p>
          <Progress value={a.progress} label="Analysis progress" />
          <p className="mt-3 text-xs text-muted">Large videos can take a minute. You can leave this page; the result will appear in your history.</p>
        </Card>
      )}

      {a.status === "failed" && (
        <Card>
          <p className="font-medium text-danger">Analysis could not be completed</p>
          <p className="mt-1 text-sm text-muted">{a.error}</p>
          <p className="mt-3 text-sm text-muted">No result is shown because none was produced. DeepShield never substitutes a guessed result.</p>
        </Card>
      )}

      {a.status === "completed" && r && (
        <>
          <Card>
            <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
              <div className="space-y-3">
                <ClassBadge value={r.assessment.classification} size="lg" />
                <p className="text-base leading-relaxed">{r.assessment.summary}</p>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-1">
                <div className="rounded-lg bg-panel-2 p-3">
                  <dt className="text-xs text-muted">Calibrated likelihood</dt>
                  <dd className="mt-0.5 font-medium">
                    {r.assessment.likelihood_calibrated && r.assessment.likelihood !== null
                      ? `${Math.round(r.assessment.likelihood * 100)}%`
                      : "Not shown"}
                  </dd>
                  {!r.assessment.likelihood_calibrated && <dd className="mt-1 text-xs text-muted">No calibrated model ran for this content, so no percentage is displayed.</dd>}
                </div>
                <div className="rounded-lg bg-panel-2 p-3">
                  <dt className="text-xs text-muted">Reliability</dt>
                  <dd className="mt-0.5 font-medium capitalize">{r.assessment.reliability}</dd>
                </div>
                <div className="rounded-lg bg-panel-2 p-3">
                  <dt className="text-xs text-muted">Synthetic origin</dt>
                  <dd className="mt-0.5 font-medium">{SYNTHETIC_LABEL[r.assessment.synthetic_origin]}</dd>
                </div>
                {r.assessment.categories.length > 0 && (
                  <div className="rounded-lg bg-panel-2 p-3">
                    <dt className="text-xs text-muted">Categories</dt>
                    <dd className="mt-1 flex flex-wrap gap-1">
                      {r.assessment.categories.map((c) => (
                        <Pill key={c}>{prettify(c)}</Pill>
                      ))}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </Card>

          {r.platform && (
            <div className="flex gap-3 rounded-xl border border-accent/30 bg-accent/8 p-4 text-sm">
              <Info className="h-5 w-5 shrink-0 text-accent" aria-hidden />
              <p>
                <strong>{r.platform.name}</strong> ({prettify(r.platform.status)}): {r.platform.detail}
              </p>
            </div>
          )}

          {r.embedded_media && r.embedded_media.length > 0 && (
            <Card title="Media found on this page">
              <ul className="space-y-2 text-sm">
                {r.embedded_media.map((m) => (
                  <li key={m.analysis_id} className="flex flex-wrap items-center gap-2">
                    <Pill>{m.kind}</Pill>
                    <span className="min-w-0 flex-1 truncate text-muted">{m.url}</span>
                    <Link href={`/analyses/${m.analysis_id}`} className="text-accent">
                      View analysis {m.analysis_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="flex items-center justify-end gap-2 text-sm">
            <span className="text-muted">View:</span>
            <div role="radiogroup" aria-label="Detail level" className="inline-flex rounded-lg border border-border p-0.5">
              {[
                ["Simple", false],
                ["Forensic", true],
              ].map(([label, val]) => (
                <button
                  key={label as string}
                  role="radio"
                  aria-checked={advanced === val}
                  onClick={() => setAdvanced(val as boolean)}
                  className={cx("rounded-md px-3 py-1", advanced === val ? "bg-accent text-accent-contrast" : "text-muted")}
                >
                  {label as string}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title={`Indicators (${shown.length})`}>
              {shown.length === 0 ? (
                <p className="text-sm text-muted">
                  The detectors that ran raised no manipulation, AI-origin or authenticity indicators.
                  {r.signals.length > 0 && " Switch to the Forensic view to see contextual notes."}
                </p>
              ) : (
                <ul className="space-y-3">
                  {shown.map((s, i) => (
                      <li key={i} className="rounded-lg border border-border p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{s.title}</span>
                          <Pill tone={DIR_TONE[s.direction]}>{DIR_LABEL[s.direction]}</Pill>
                          <Pill>{s.strength}</Pill>
                          {s.timestamp_s !== null && <Pill tone="accent">at {s.timestamp_s}s</Pill>}
                        </div>
                        <p className="mt-1.5 text-sm text-muted">{s.detail}</p>
                        {advanced && (
                          <p className="mt-2 font-mono text-[11px] text-muted">
                            {s.detector} · {s.id}
                            {Object.keys(s.evidence ?? {}).length > 0 && ` · ${JSON.stringify(s.evidence)}`}
                          </p>
                        )}
                      </li>
                    ))}
                </ul>
              )}
            </Card>

            <Card title="Evidence">
              {r.evidence.length === 0 ? (
                <p className="text-sm text-muted">No visual evidence was produced for this content type.</p>
              ) : r.media.kind === "video" ? (
                <VideoTimeline
                  analysisId={a.id}
                  frames={r.evidence.filter((e) => e.kind === "frame")}
                  signals={r.signals}
                  duration={Number(r.facts?.video_forensics?.duration_s ?? 0)}
                />
              ) : (
                <div className="space-y-4">
                  {r.evidence.map((e) => (
                    <figure key={e.name}>
                      <EvidenceImage analysisId={a.id} item={e} />
                      <figcaption className="mt-1.5 text-xs text-muted">{e.caption}</figcaption>
                    </figure>
                  ))}
                  <p className="text-xs text-muted">Derived images only. The original file is kept separately and never modified.</p>
                </div>
              )}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Recommended next steps">
              <ol className="list-decimal space-y-1.5 pl-5 text-sm">
                {r.next_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            </Card>
            <Card title="Limitations">
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
                {r.limitations.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </Card>
          </div>

          {advanced && (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Detection methods">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-muted">
                      <tr>
                        <th className="py-1.5 pr-3 font-medium">Detector</th>
                        <th className="py-1.5 pr-3 font-medium">Status</th>
                        <th className="py-1.5 font-medium">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {r.detectors.map((d) => (
                        <tr key={d.name}>
                          <td className="py-2 pr-3 font-mono text-xs">
                            {d.name} <span className="text-muted">v{d.version}</span>
                          </td>
                          <td className="py-2 pr-3">
                            <Pill tone={d.status === "ok" ? "ok" : d.status === "error" ? "danger" : "unc"}>{d.status}</Pill>
                          </td>
                          <td className="py-2 text-xs text-muted">{d.reason ?? (d.calibrated ? "calibrated" : "heuristic, uncalibrated")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
              <Card title="Media & raw facts">
                <dl className="mb-3 grid grid-cols-[120px_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-muted">Type</dt>
                  <dd>{r.media.mime}</dd>
                  <dt className="text-muted">Size</dt>
                  <dd>{fmtBytes(r.media.size)}</dd>
                  <dt className="text-muted">SHA-256</dt>
                  <dd className="break-all font-mono text-xs">{r.media.sha256}</dd>
                  {r.media.source_url && (
                    <>
                      <dt className="text-muted">Source</dt>
                      <dd className="break-all text-xs">
                        <a href={r.media.source_url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-accent">
                          {r.media.source_url} <ExternalLink className="h-3 w-3" aria-hidden />
                        </a>
                      </dd>
                    </>
                  )}
                  {a.page_url && (
                    <>
                      <dt className="text-muted">Found on</dt>
                      <dd className="break-all text-xs">{a.page_url}</dd>
                    </>
                  )}
                </dl>
                <pre className="max-h-80 overflow-auto rounded-lg bg-panel-2 p-3 text-[11px] leading-relaxed">{JSON.stringify(r.facts, null, 2)}</pre>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AddToCase({ analysisId }: { analysisId: string }) {
  const [open, setOpen] = useState(false);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (open) api<CaseSummary[]>("/cases").then(setCases).catch(() => {});
  }, [open]);

  const add = async (caseId: number) => {
    await api(`/cases/${caseId}/items`, { method: "POST", json: { analysis_id: analysisId } });
    setMsg("Added to investigation.");
  };
  const create = async () => {
    if (!title.trim()) return;
    await api("/cases", { method: "POST", json: { title: title.trim(), analysis_id: analysisId } });
    setMsg("Investigation created.");
    setTitle("");
  };

  return (
    <div className="relative">
      <Button variant="secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
        <FolderPlus className="h-4 w-4" aria-hidden /> Add to case
      </Button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-72 space-y-3 rounded-xl border border-border bg-panel p-3 shadow-xl">
          {cases.filter((c) => c.status === "open").length > 0 && (
            <ul className="max-h-40 space-y-1 overflow-auto">
              {cases
                .filter((c) => c.status === "open")
                .map((c) => (
                  <li key={c.id}>
                    <button onClick={() => add(c.id)} className="w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-panel-2">
                      {c.title}
                    </button>
                  </li>
                ))}
            </ul>
          )}
          <div className="flex gap-2">
            <input className={inputCls} placeholder="New investigation title" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="New investigation title" />
            <Button onClick={create}>Create</Button>
          </div>
          {msg && (
            <p className="text-xs text-ok" role="status">
              {msg}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
