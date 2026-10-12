"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Button, Card, ClassBadge, Empty, ErrorNote, Pill, Spinner, StatusPill, inputCls } from "@/components/ui";
import { api, type AnalysisSummary } from "@/lib/api";
import { CLASS_META, fmtDate, sourceLabel } from "@/lib/format";

interface Page {
  items: AnalysisSummary[];
  total: number;
  page: number;
  page_size: number;
}

function HistoryInner() {
  const params = useSearchParams();
  const [cls, setCls] = useState(params.get("classification") ?? "");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const qs = new URLSearchParams({ page: String(page), page_size: "20" });
    if (cls) qs.set("classification", cls);
    if (kind) qs.set("kind", kind);
    if (q.trim()) qs.set("q", q.trim());
    const t = setTimeout(() => {
      api<Page>(`/analyses?${qs}`)
        .then(setData)
        .catch((e) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [cls, kind, q, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Analysis history" subtitle="Every scan you've run. Deleting an analysis also removes its stored media and evidence." />
      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <input className={`${inputCls} max-w-xs`} placeholder="Search ID or URL" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search analyses" />
          <select className={`${inputCls} w-auto`} value={cls} onChange={(e) => { setCls(e.target.value); setPage(1); }} aria-label="Filter by classification">
            <option value="">All classifications</option>
            {Object.entries(CLASS_META).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
          <select className={`${inputCls} w-auto`} value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} aria-label="Filter by content type">
            <option value="">All types</option>
            {["image", "video", "audio", "html"].map((k) => (
              <option key={k} value={k}>
                {k === "html" ? "web page" : k}
              </option>
            ))}
          </select>
        </div>
        <ErrorNote message={error} />
        {!data ? (
          <Spinner />
        ) : data.items.length === 0 ? (
          <Empty title="No analyses match these filters" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-2 pr-3 font-medium">ID</th>
                  <th className="py-2 pr-3 font-medium">Source</th>
                  <th className="py-2 pr-3 font-medium">Type</th>
                  <th className="py-2 pr-3 font-medium">Result</th>
                  <th className="py-2 font-medium">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.items.map((a) => (
                  <tr key={a.id} className="hover:bg-panel-2/60">
                    <td className="py-2.5 pr-3">
                      <Link href={`/analyses/${a.id}`} className="font-mono text-xs text-accent">
                        {a.id}
                      </Link>
                    </td>
                    <td className="max-w-xs truncate py-2.5 pr-3" title={a.source_url ?? a.file_name ?? ""}>
                      {sourceLabel(a)}
                    </td>
                    <td className="py-2.5 pr-3">
                      <Pill>{a.kind ?? "…"}</Pill>
                    </td>
                    <td className="py-2.5 pr-3">{a.status === "completed" ? <ClassBadge value={a.classification} /> : <StatusPill status={a.status} />}</td>
                    <td className="py-2.5 text-xs text-muted">{fmtDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && pages > 1 && (
          <div className="mt-4 flex items-center justify-end gap-3 text-sm">
            <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <span className="text-muted">
              Page {page} of {pages}
            </span>
            <Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next
            </Button>
          </div>
        )}
      </Card>
    </>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <HistoryInner />
    </Suspense>
  );
}
