"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader, useUser } from "@/components/AppShell";
import { Button, Card, ClassBadge, Empty, ErrorNote, Pill, Spinner } from "@/components/ui";
import { api, type AlertItem } from "@/lib/api";
import { fmtDate } from "@/lib/format";

export default function AlertsPage() {
  const { refresh } = useUser();
  const [alerts, setAlerts] = useState<AlertItem[] | null>(null);
  const [filter, setFilter] = useState<"new" | "all">("new");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<AlertItem[]>(filter === "new" ? "/alerts?state=new" : "/alerts")
      .then(setAlerts)
      .catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, [filter]);

  const setState = async (id: number, state: string) => {
    await api(`/alerts/${id}`, { method: "PATCH", json: { state } });
    load();
    refresh();
  };

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle="Raised when an analysis meets your risk threshold (Settings). Alerts are never acted on automatically: nothing is deleted, reported or flagged publicly."
        action={
          <div className="inline-flex rounded-lg border border-border p-0.5 text-sm" role="radiogroup" aria-label="Alert filter">
            {(["new", "all"] as const).map((f) => (
              <button key={f} role="radio" aria-checked={filter === f} onClick={() => setFilter(f)} className={`rounded-md px-3 py-1 ${filter === f ? "bg-accent text-accent-contrast" : "text-muted"}`}>
                {f === "new" ? "New" : "All"}
              </button>
            ))}
          </div>
        }
      />
      <ErrorNote message={error} />
      {!alerts ? (
        <Spinner />
      ) : alerts.length === 0 ? (
        <Empty title={filter === "new" ? "No new alerts" : "No alerts yet"} />
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {alerts.map((al) => (
              <li key={al.id} className="flex flex-wrap items-center gap-3 py-3">
                <ClassBadge value={al.level} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{al.title}</p>
                  <p className="text-xs text-muted">{fmtDate(al.created_at)}</p>
                </div>
                {al.state !== "new" && <Pill>{al.state}</Pill>}
                {al.analysis_id && (
                  <Link href={`/analyses/${al.analysis_id}`} className="text-sm text-accent">
                    Review
                  </Link>
                )}
                {al.state === "new" && (
                  <>
                    <Button variant="secondary" onClick={() => setState(al.id, "acknowledged")}>
                      Acknowledge
                    </Button>
                    <Button variant="ghost" onClick={() => setState(al.id, "dismissed")}>
                      Dismiss
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
