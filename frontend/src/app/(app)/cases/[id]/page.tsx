"use client";

import { ArrowLeft, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, Card, ClassBadge, Empty, ErrorNote, Spinner, StatusPill, inputCls } from "@/components/ui";
import { api, type CaseDetail } from "@/lib/api";
import { fmtDate, sourceLabel } from "@/lib/format";

const STATUSES = ["open", "reported", "resolved", "dismissed"] as const;

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [c, setC] = useState<CaseDetail | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<CaseDetail>(`/cases/${id}`).then(setC).catch((e) => setError(e.message)), [id]);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (fn: () => Promise<CaseDetail | void>) => {
    try {
      const r = await fn();
      if (r) setC(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  };

  const addNote = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await api<CaseDetail>(`/cases/${id}/notes`, { method: "POST", json: { body: note } });
      setNote("");
      return r;
    });
  };

  if (!c) return error ? <ErrorNote message={error} /> : <Spinner />;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/cases" className="mb-2 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Investigations
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{c.title}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm text-muted" htmlFor="case-status">
              Status
            </label>
            <select
              id="case-status"
              className={`${inputCls} w-auto`}
              value={c.status}
              onChange={(e) => run(() => api<CaseDetail>(`/cases/${id}`, { method: "PATCH", json: { status: e.target.value } }))}
            >
              {STATUSES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <Button
              variant="danger"
              onClick={() =>
                confirm("Delete this investigation? The analyses themselves are kept.") &&
                run(async () => {
                  await api(`/cases/${id}`, { method: "DELETE" });
                  router.replace("/cases");
                })
              }
            >
              Delete
            </Button>
          </div>
        </div>
        <p className="mt-1 text-sm text-muted">Created {fmtDate(c.created_at)}. Marking a case “reported” records it for your tracking only; DeepShield never contacts platforms on your behalf.</p>
      </div>
      <ErrorNote message={error} />

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Card title={`Evidence items (${c.items.length})`}>
          {c.items.length === 0 ? (
            <Empty title="No analyses in this case">Open an analysis and choose “Add to case”.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {c.items.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3 py-2.5">
                  <Link href={`/analyses/${a.id}`} className="font-mono text-xs text-accent">
                    {a.id}
                  </Link>
                  <span className="min-w-0 flex-1 truncate text-sm">{sourceLabel(a)}</span>
                  {a.status === "completed" ? <ClassBadge value={a.classification} /> : <StatusPill status={a.status} />}
                  <button
                    onClick={() => run(() => api<CaseDetail>(`/cases/${id}/items/${a.id}`, { method: "DELETE" }))}
                    className="rounded p-1 text-muted hover:text-danger"
                    aria-label={`Remove ${a.id} from case`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Investigation notes">
          <form onSubmit={addNote} className="mb-4 space-y-2">
            <textarea className={`${inputCls} min-h-24`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Findings, report reference numbers, contacts…" required aria-label="New note" />
            <Button type="submit">Add note</Button>
          </form>
          <ol className="space-y-3">
            {[...c.notes].reverse().map((n) => (
              <li key={n.id} className="rounded-lg bg-panel-2 p-3 text-sm">
                <p className="whitespace-pre-wrap">{n.body}</p>
                <p className="mt-1 text-xs text-muted">{fmtDate(n.created_at)}</p>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
