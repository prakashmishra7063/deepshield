"use client";

import { AlertTriangle, Bell, FileSearch, FolderKanban, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/AppShell";
import QuickScan from "@/components/QuickScan";
import { Card, ClassBadge, Empty, ErrorNote, Pill, Spinner, StatusPill } from "@/components/ui";
import { api, type AnalysisSummary } from "@/lib/api";
import { fmtDate, sourceLabel } from "@/lib/format";

interface Summary {
  total: number;
  completed: number;
  in_progress: number;
  failed: number;
  potentially_manipulated: number;
  high_risk: number;
  by_kind: Record<string, number>;
  trend: { date: string; total: number; flagged: number }[];
  recent: AnalysisSummary[];
  open_cases: number;
  new_alerts: number;
}

interface Health {
  detectors: { name: string; available: boolean; category: string; reason: string | null; kinds: string[] }[];
  models_configured: boolean;
  ffmpeg: boolean;
  queue_depth: number;
}

const tooltipStyle = {
  background: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  color: "var(--text)",
  fontSize: 12,
};

function Stat({ label, value, icon: Icon, tone, href }: { label: string; value: number; icon: typeof Bell; tone?: string; href: string }) {
  return (
    <Link href={href} className="group rounded-xl border border-border bg-panel p-4 transition hover:border-accent">
      <div className="flex items-center justify-between text-sm text-muted">
        {label}
        <Icon className={`h-4 w-4 ${tone ?? "text-accent"}`} aria-hidden />
      </div>
      <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
    </Link>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Summary | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      api<Summary>("/dashboard/summary")
        .then(setData)
        .catch((e) => setError(e.message));
    load();
    api<Health>("/system/health").then(setHealth).catch(() => {});
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  const kinds = data ? Object.entries(data.by_kind).map(([kind, count]) => ({ kind, count })) : [];
  const flagged = data ? data.potentially_manipulated + data.high_risk : 0;

  return (
    <>
      <PageHeader title="Security overview" subtitle="Your content analyses, findings and investigations at a glance." />
      <ErrorNote message={error} />
      {!data ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Stat label="Content analyzed" value={data.total} icon={FileSearch} href="/history" />
            <Stat label="Potentially manipulated" value={flagged} icon={AlertTriangle} tone="text-warn" href="/history?classification=potentially_manipulated" />
            <Stat label="High-risk findings" value={data.high_risk} icon={ShieldAlert} tone="text-danger" href="/history?classification=high_risk" />
            <Stat label="New alerts" value={data.new_alerts} icon={Bell} href="/alerts" />
            <Stat label="Open investigations" value={data.open_cases} icon={FolderKanban} href="/cases" />
          </div>

          <QuickScan />

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Detection trend (last 30 active days)" className="lg:col-span-2">
              {data.trend.length === 0 ? (
                <Empty title="No completed analyses yet" />
              ) : (
                <div className="h-64" role="img" aria-label="Line chart of analyses per day and flagged analyses per day">
                  <ResponsiveContainer>
                    <LineChart data={data.trend} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="0" vertical={false} />
                      <XAxis dataKey="date" tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
                      <YAxis allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }} />
                      <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted)" }} />
                      <Line type="monotone" name="Analyzed" dataKey="total" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 5 }} />
                      <Line type="monotone" name="Flagged" dataKey="flagged" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 5 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card title="Content types">
              {kinds.length === 0 ? (
                <Empty title="Nothing analyzed yet" />
              ) : (
                <div className="h-64" role="img" aria-label={`Bar chart of analyses by content type: ${kinds.map((k) => `${k.kind} ${k.count}`).join(", ")}`}>
                  <ResponsiveContainer>
                    <BarChart data={kinds} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                      <CartesianGrid stroke="var(--border)" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} />
                      <YAxis type="category" dataKey="kind" tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} axisLine={false} width={56} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--panel-2)" }} />
                      <Bar dataKey="count" name="Analyses" fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={18} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Recent analyses" className="lg:col-span-2" action={<Link href="/history" className="text-sm text-accent">View all</Link>}>
              {data.recent.length === 0 ? (
                <Empty title="No analyses yet">Upload a file or paste a URL above to start.</Empty>
              ) : (
                <ul className="divide-y divide-border">
                  {data.recent.map((a) => (
                    <li key={a.id}>
                      <Link href={`/analyses/${a.id}`} className="flex flex-wrap items-center gap-3 py-2.5 hover:text-accent">
                        <span className="font-mono text-xs text-muted">{a.id}</span>
                        <span className="min-w-0 flex-1 truncate text-sm">{sourceLabel(a)}</span>
                        <Pill>{a.kind ?? "…"}</Pill>
                        {a.status === "completed" ? <ClassBadge value={a.classification} /> : <StatusPill status={a.status} />}
                        <span className="hidden text-xs text-muted sm:inline">{fmtDate(a.created_at)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="System & model availability" action={<Link href="/system" className="text-sm text-accent">Details</Link>}>
              {!health ? (
                <Spinner />
              ) : (
                <ul className="space-y-2 text-sm">
                  {health.detectors.map((d) => (
                    <li key={d.name} className="flex items-center justify-between gap-2">
                      <span className="truncate">{d.name.replace(/_/g, " ")}</span>
                      <Pill tone={d.available ? "ok" : "unc"}>{d.available ? "available" : "unavailable"}</Pill>
                    </li>
                  ))}
                  {!health.models_configured && (
                    <li className="rounded-lg border border-warn/30 bg-warn/10 p-2 text-xs text-warn">
                      No deep-learning model is configured. Results rely on forensic heuristics and provenance only, and
                      no likelihood percentage is shown.
                    </li>
                  )}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
