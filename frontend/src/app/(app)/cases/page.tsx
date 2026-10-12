"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/AppShell";
import { Button, Card, Empty, ErrorNote, Pill, Spinner, inputCls } from "@/components/ui";
import { api, type CaseSummary } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const CASE_TONE: Record<string, string> = { open: "accent", reported: "warn", resolved: "ok", dismissed: "unc" };

export default function CasesPage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () => api<CaseSummary[]>("/cases").then(setCases).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api("/cases", { method: "POST", json: { title } });
      setTitle("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create");
    }
  };

  return (
    <>
      <PageHeader title="Investigations" subtitle="Group related analyses, keep notes and track what you've reported to platforms." />
      <Card className="mb-6">
        <form onSubmit={create} className="flex flex-wrap gap-3">
          <input className={`${inputCls} max-w-md flex-1`} placeholder="e.g. Impersonation of our CEO on video platforms" value={title} onChange={(e) => setTitle(e.target.value)} required aria-label="Investigation title" />
          <Button type="submit">New investigation</Button>
        </form>
      </Card>
      <ErrorNote message={error} />
      {!cases ? (
        <Spinner />
      ) : cases.length === 0 ? (
        <Empty title="No investigations yet">Create one here, or use “Add to case” from any analysis.</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cases.map((c) => (
            <Link key={c.id} href={`/cases/${c.id}`} className="rounded-xl border border-border bg-panel p-4 transition hover:border-accent">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-medium">{c.title}</h2>
                <Pill tone={CASE_TONE[c.status]}>{c.status}</Pill>
              </div>
              <p className="mt-3 text-sm text-muted">
                {c.item_count} item{c.item_count === 1 ? "" : "s"} · updated {fmtDate(c.updated_at)}
              </p>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
