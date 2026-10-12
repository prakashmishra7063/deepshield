"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader, useUser } from "@/components/AppShell";
import { Button, Card, Empty, ErrorNote, Pill, Spinner, cx, inputCls } from "@/components/ui";
import { api, type Plan, type Usage } from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/format";

interface Overview {
  users: number;
  suspended_users: number;
  unverified_users: number;
  workspaces: number;
  team_workspaces: number;
  scans_this_month: number;
  failed_this_month: number;
  queued: number;
  by_plan: Record<string, number>;
  list_price_mrr_cents: number;
  signups_30d: { date: string; count: number }[];
  scans_30d: { date: string; count: number }[];
}
interface AdminUser {
  id: number;
  email: string;
  role: string;
  status: string;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
  workspaces: number;
  scans_this_month: number;
}
interface AdminOrg {
  id: number;
  name: string;
  kind: string;
  status: string;
  plan_id: string;
  plan_name: string;
  credits: number;
  scan_quota_override: number | null;
  members: number;
  owner_email: string | null;
  usage: Usage;
  created_at: string;
}
interface AuditRow {
  id: number;
  user_id: number | null;
  action: string;
  target: string | null;
  ip: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}
type PageOf<T> = { items: T[]; total: number; page: number; page_size: number };

const TABS = ["Overview", "Customers", "Workspaces", "Plans", "Settings", "Audit log"] as const;
type Tab = (typeof TABS)[number];

const tip = { background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", fontSize: 12 };

export default function AdminPage() {
  const { user } = useUser();
  const [tab, setTab] = useState<Tab>("Overview");
  if (user && user.role !== "owner") return <ErrorNote message="The owner console is only available to the platform owner." />;
  return (
    <>
      <PageHeader
        title="Owner console"
        subtitle="Manage customers, workspaces, plans and platform settings. Customers' uploaded media and results stay private and aren't visible here."
      />
      <div role="tablist" aria-label="Owner console sections" className="mb-6 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cx("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm", tab === t ? "border-accent font-medium text-accent" : "border-transparent text-muted hover:text-text")}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <OverviewTab />}
      {tab === "Customers" && <CustomersTab />}
      {tab === "Workspaces" && <WorkspacesTab />}
      {tab === "Plans" && <PlansTab />}
      {tab === "Settings" && <SettingsTab />}
      {tab === "Audit log" && <AuditTab />}
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

function MiniBars({ data, label }: { data: { date: string; count: number }[]; label: string }) {
  if (!data.length) return <Empty title="No activity in the last 30 days" />;
  return (
    <div className="h-48" role="img" aria-label={`${label} per day, last 30 days`}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "var(--muted)", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
          <YAxis allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 10 }} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={tip} cursor={{ fill: "var(--panel-2)" }} />
          <Bar dataKey="count" name={label} fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function OverviewTab() {
  const [o, setO] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Overview>("/admin/overview").then(setO).catch((e) => setError(e.message));
  }, []);
  if (!o) return error ? <ErrorNote message={error} /> : <Spinner />;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Customers" value={o.users} hint={`${o.unverified_users} unverified · ${o.suspended_users} suspended`} />
        <Stat label="Workspaces" value={o.workspaces} hint={`${o.team_workspaces} team workspaces`} />
        <Stat label="Scans this month" value={o.scans_this_month} hint={`${o.failed_this_month} failed · ${o.queued} in queue`} />
        <Stat label="Plan value / month" value={fmtMoney(o.list_price_mrr_cents)} hint="List price of assigned plans (not collected payments)" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Sign-ups (30 days)">
          <MiniBars data={o.signups_30d} label="Sign-ups" />
        </Card>
        <Card title="Scans (30 days)">
          <MiniBars data={o.scans_30d} label="Scans" />
        </Card>
      </div>
      <Card title="Workspaces by plan">
        <ul className="flex flex-wrap gap-3 text-sm">
          {Object.entries(o.by_plan).map(([p, n]) => (
            <li key={p} className="rounded-lg bg-panel-2 px-3 py-2">
              <span className="font-medium">{p}</span> <span className="text-muted">· {n}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function useListing<T>(path: string, q: string, page: number) {
  const [data, setData] = useState<PageOf<T> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    const qs = new URLSearchParams({ page: String(page) });
    if (q.trim()) qs.set("q", q.trim());
    return api<PageOf<T>>(`${path}?${qs}`).then(setData).catch((e) => setError(e.message));
  }, [path, q, page]);
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);
  return { data, error, setError, load };
}

function Pager({ data, page, setPage }: { data: PageOf<unknown>; page: number; setPage: (n: number) => void }) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  if (pages <= 1) return null;
  return (
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
  );
}

function CustomersTab() {
  const { user: me } = useUser();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, setError, load } = useListing<AdminUser>("/admin/users", q, page);
  const [notice, setNotice] = useState<string | null>(null);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(ok);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };

  return (
    <Card>
      <input className={`${inputCls} mb-4 max-w-sm`} placeholder="Search by email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search customers" />
      <ErrorNote message={error} />
      {notice && <p className="mb-3 text-sm text-ok" role="status">{notice}</p>}
      {!data ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        <Empty title="No customers match" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Email</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Scans (month)</th>
                <th className="py-2 pr-3 font-medium">Joined</th>
                <th className="py-2 pr-3 font-medium">Last login</th>
                <th className="py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.items.map((u) => (
                <tr key={u.id}>
                  <td className="py-2.5 pr-3">
                    {u.email} {u.role === "owner" && <Pill tone="accent">owner</Pill>}
                    <span className="block text-xs text-muted">{u.workspaces} workspace(s)</span>
                  </td>
                  <td className="py-2.5 pr-3">
                    <div className="flex flex-wrap gap-1">
                      <Pill tone={u.status === "active" ? "ok" : "danger"}>{u.status}</Pill>
                      {!u.email_verified && <Pill tone="warn">unverified</Pill>}
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 tabular-nums">{u.scans_this_month}</td>
                  <td className="py-2.5 pr-3 text-xs text-muted">{fmtDate(u.created_at)}</td>
                  <td className="py-2.5 pr-3 text-xs text-muted">{u.last_login_at ? fmtDate(u.last_login_at) : "never"}</td>
                  <td className="py-2.5">
                    {u.id !== me?.id && (
                      <div className="flex flex-wrap gap-1">
                        {u.status === "active" ? (
                          <Button variant="secondary" onClick={() => confirm(`Suspend ${u.email}? They will be signed out immediately.`) && act(() => api(`/admin/users/${u.id}`, { method: "PATCH", json: { status: "suspended" } }), "Customer suspended.")}>
                            Suspend
                          </Button>
                        ) : (
                          <Button variant="secondary" onClick={() => act(() => api(`/admin/users/${u.id}`, { method: "PATCH", json: { status: "active" } }), "Customer reactivated.")}>
                            Reactivate
                          </Button>
                        )}
                        {!u.email_verified && (
                          <Button variant="ghost" onClick={() => act(() => api(`/admin/users/${u.id}`, { method: "PATCH", json: { email_verified: true } }), "Marked as verified.")}>
                            Verify
                          </Button>
                        )}
                        <Button variant="ghost" onClick={() => act(() => api(`/admin/users/${u.id}/send-reset`, { method: "POST" }), "Password reset email sent.")}>
                          Send reset
                        </Button>
                        <Button variant="ghost" onClick={() => act(() => api(`/admin/users/${u.id}/revoke-sessions`, { method: "POST" }), "Sessions and API tokens revoked.")}>
                          Sign out
                        </Button>
                        <Button
                          variant="danger"
                          onClick={() =>
                            prompt(`Type the customer's email to permanently delete ${u.email} and their personal data:`) === u.email &&
                            act(() => api(`/admin/users/${u.id}`, { method: "DELETE" }), "Customer deleted.")
                          }
                        >
                          Delete
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pager data={data} page={page} setPage={setPage} />}
    </Card>
  );
}

function WorkspacesTab() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, setError, load } = useListing<AdminOrg>("/admin/orgs", q, page);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    api<Plan[]>("/admin/plans").then(setPlans).catch(() => {});
  }, []);

  const patch = async (id: number, body: Record<string, unknown>, ok: string) => {
    setError(null);
    setNotice(null);
    try {
      await api(`/admin/orgs/${id}`, { method: "PATCH", json: body });
      setNotice(ok);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };

  return (
    <Card>
      <input className={`${inputCls} mb-4 max-w-sm`} placeholder="Search name or member email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search workspaces" />
      <ErrorNote message={error} />
      {notice && <p className="mb-3 text-sm text-ok" role="status">{notice}</p>}
      {!data ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        <Empty title="No workspaces match" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Workspace</th>
                <th className="py-2 pr-3 font-medium">Plan</th>
                <th className="py-2 pr-3 font-medium">Usage</th>
                <th className="py-2 pr-3 font-medium">Credits</th>
                <th className="py-2 pr-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.items.map((o) => (
                <tr key={o.id}>
                  <td className="py-2.5 pr-3">
                    <span className="font-medium">{o.name}</span>
                    <span className="block text-xs text-muted">
                      {o.kind} · {o.members} member(s) · {o.owner_email ?? "no owner"}
                    </span>
                  </td>
                  <td className="py-2.5 pr-3">
                    <select className={`${inputCls} w-auto py-1`} value={o.plan_id} aria-label={`Plan for ${o.name}`} onChange={(e) => patch(o.id, { plan_id: e.target.value }, "Plan changed.")}>
                      {plans.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2.5 pr-3 tabular-nums">
                    {o.usage.used} / {o.usage.limit < 0 ? "∞" : o.usage.limit}
                    {o.scan_quota_override !== null && <span className="block text-xs text-warn">custom quota</span>}
                    <button
                      className="block text-xs text-accent underline"
                      onClick={() => {
                        const v = prompt("Custom monthly scan quota (blank = plan default, -1 = unlimited):", o.scan_quota_override?.toString() ?? "");
                        if (v === null) return;
                        patch(o.id, v.trim() === "" ? { clear_quota_override: true } : { scan_quota_override: Number(v) }, "Quota updated.");
                      }}
                    >
                      Set quota
                    </button>
                  </td>
                  <td className="py-2.5 pr-3 tabular-nums">
                    {o.credits}
                    <button
                      className="block text-xs text-accent underline"
                      onClick={() => {
                        const v = prompt("Add (or remove with a minus sign) scan credits:", "100");
                        if (v && !Number.isNaN(Number(v))) patch(o.id, { credits_delta: Number(v) }, "Credits updated.");
                      }}
                    >
                      Adjust
                    </button>
                  </td>
                  <td className="py-2.5 pr-3">
                    <Pill tone={o.status === "active" ? "ok" : "danger"}>{o.status}</Pill>
                    <button
                      className="ml-2 text-xs text-accent underline"
                      onClick={() => patch(o.id, { status: o.status === "active" ? "suspended" : "active" }, o.status === "active" ? "Workspace suspended." : "Workspace reactivated.")}
                    >
                      {o.status === "active" ? "Suspend" : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pager data={data} page={page} setPage={setPage} />}
    </Card>
  );
}

const EMPTY_PLAN = { id: "", name: "", description: "", monthly_scans: 100, max_upload_mb: 25, max_members: 1, price_monthly_cents: 0, public: true, sort: 5 };

function PlansTab() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [draft, setDraft] = useState(EMPTY_PLAN);
  const [error, setError] = useState<string | null>(null);
  const load = () => api<Plan[]>("/admin/plans").then(setPlans).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const save = async (p: Plan, patch: Partial<Plan>) => {
    setError(null);
    try {
      await api(`/admin/plans/${p.id}`, { method: "PATCH", json: patch });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };
  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/admin/plans", { method: "POST", json: draft });
      setDraft(EMPTY_PLAN);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  const num = (p: Plan, key: keyof Plan, label: string) => (
    <input
      type="number"
      className={`${inputCls} w-24 py-1`}
      defaultValue={p[key] as number}
      aria-label={`${label} for ${p.name}`}
      onBlur={(e) => Number(e.target.value) !== p[key] && save(p, { [key]: Number(e.target.value) })}
    />
  );

  return (
    <div className="space-y-6">
      <ErrorNote message={error} />
      <Card title="Plans">
        {!plans ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-2 pr-3 font-medium">Plan</th>
                  <th className="py-2 pr-3 font-medium">Scans / month</th>
                  <th className="py-2 pr-3 font-medium">Max upload MB</th>
                  <th className="py-2 pr-3 font-medium">Seats</th>
                  <th className="py-2 pr-3 font-medium">Price (cents)</th>
                  <th className="py-2 font-medium">Public</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {plans.map((p) => (
                  <tr key={p.id}>
                    <td className="py-2.5 pr-3">
                      <span className="font-medium">{p.name}</span> <span className="font-mono text-xs text-muted">{p.id}</span>
                      <span className="block text-xs text-muted">{fmtMoney(p.price_monthly_cents, p.currency)}</span>
                    </td>
                    <td className="py-2.5 pr-3">{num(p, "monthly_scans", "Scans")}</td>
                    <td className="py-2.5 pr-3">{num(p, "max_upload_mb", "Max upload")}</td>
                    <td className="py-2.5 pr-3">{num(p, "max_members", "Seats")}</td>
                    <td className="py-2.5 pr-3">{num(p, "price_monthly_cents", "Price")}</td>
                    <td className="py-2.5">
                      <input type="checkbox" checked={p.public} onChange={(e) => save(p, { public: e.target.checked })} aria-label={`${p.name} is public`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-muted">Use -1 scans for unlimited. Changes apply immediately to every workspace on that plan. Edits save when a field loses focus.</p>
      </Card>
      <Card title="Create a plan">
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              ["id", "ID (lowercase)", "text"],
              ["name", "Name", "text"],
              ["monthly_scans", "Scans / month", "number"],
              ["max_upload_mb", "Max upload MB", "number"],
              ["max_members", "Seats", "number"],
              ["price_monthly_cents", "Price in cents", "number"],
              ["description", "Description", "text"],
            ] as const
          ).map(([k, label, type]) => (
            <label key={k} className="text-sm">
              {label}
              <input
                className={`${inputCls} mt-1`}
                type={type}
                required={k !== "description"}
                value={draft[k] as string | number}
                onChange={(e) => setDraft({ ...draft, [k]: type === "number" ? Number(e.target.value) : e.target.value })}
              />
            </label>
          ))}
          <div className="flex items-end">
            <Button type="submit">Create plan</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

interface EmailStatus {
  delivery: "smtp" | "outbox" | "disabled";
  host: string | null;
  port: number;
  from: string | null;
  app_url: string;
  outbox_dir: string | null;
}

function EmailCard() {
  const [st, setSt] = useState<EmailStatus | null>(null);
  const [result, setResult] = useState<{ ok: boolean; error: string | null; to: string; mode: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<EmailStatus>("/admin/email").then(setSt).catch(() => {});
  }, []);
  const test = async () => {
    setBusy(true);
    setResult(null);
    try {
      setResult(await api("/admin/email/test", { method: "POST" }));
    } catch (e) {
      setResult({ ok: false, error: e instanceof Error ? e.message : "Failed", to: "", mode: "" });
    } finally {
      setBusy(false);
    }
  };
  if (!st) return <Spinner />;
  return (
    <Card title="Email delivery">
      <div className="space-y-3 text-sm">
        {st.delivery === "smtp" ? (
          <p>
            <Pill tone="ok">Connected</Pill> Sending through <span className="font-mono">{st.host}:{st.port}</span> as{" "}
            <span className="font-mono">{st.from}</span>.
          </p>
        ) : (
          <div className="rounded-lg border border-warn/30 bg-warn/10 p-3">
            <p className="font-medium text-warn">Not configured: emails are not being delivered</p>
            <p className="mt-1">
              Verification, password-reset and invite emails are being saved as files instead of sent
              {st.outbox_dir && (
                <>
                  {" "}
                  (in <span className="break-all font-mono text-xs">{st.outbox_dir}</span>)
                </>
              )}
              . Until this is set up, email verification is paused so nobody gets locked out. It switches back on
              automatically once email works.
            </p>
            <p className="mt-2">
              To fix it, add your email provider&apos;s SMTP settings (<span className="font-mono">DS_SMTP_HOST</span>,{" "}
              <span className="font-mono">DS_SMTP_PORT</span>, <span className="font-mono">DS_SMTP_USER</span>,{" "}
              <span className="font-mono">DS_SMTP_PASSWORD</span>, <span className="font-mono">DS_SMTP_FROM</span>) to{" "}
              <span className="font-mono">backend/.env</span> and restart the API. See docs/DEPLOYMENT.md → Email.
            </p>
          </div>
        )}
        <p className="text-muted">
          Links in emails point to <span className="font-mono">{st.app_url}</span> (<span className="font-mono">DS_APP_URL</span>).
        </p>
        <Button variant="secondary" onClick={test} loading={busy}>
          Send test email to me
        </Button>
        {result && (
          <p role="status" className={result.ok ? "text-ok" : "text-danger"}>
            {result.ok
              ? result.mode === "smtp"
                ? `Test email sent to ${result.to}. Check the inbox (and spam).`
                : `Saved to the outbox folder, not delivered, because SMTP isn't configured.`
              : result.error}
          </p>
        )}
      </div>
    </Card>
  );
}

function SettingsTab() {
  const [s, setS] = useState<{ signups_open: boolean; require_email_verification: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<typeof s>("/admin/settings").then(setS).catch((e) => setError(e.message));
  }, []);
  const save = async (patch: Record<string, boolean>) => {
    try {
      setS(await api<typeof s>("/admin/settings", { method: "PATCH", json: patch }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };
  if (!s) return error ? <ErrorNote message={error} /> : <Spinner />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
    <EmailCard />
    <Card title="Platform settings">
      <div className="space-y-4 text-sm">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={s.signups_open} onChange={(e) => save({ signups_open: e.target.checked })} />
          <span>
            <span className="font-medium">Open sign-ups</span>
            <span className="block text-muted">When off, only people with a workspace invitation can create an account.</span>
          </span>
        </label>
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={s.require_email_verification} onChange={(e) => save({ require_email_verification: e.target.checked })} />
          <span>
            <span className="font-medium">Require email verification before scanning</span>
            <span className="block text-muted">
              Recommended. Stops throwaway accounts from using your scan capacity. Only enforced while email delivery is
              connected.
            </span>
          </span>
        </label>
        <ErrorNote message={error} />
      </div>
    </Card>
    </div>
  );
}

function AuditTab() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [action, setAction] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      api<AuditRow[]>(`/admin/audit?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`)
        .then(setRows)
        .catch((e) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [action]);
  return (
    <Card>
      <input className={`${inputCls} mb-4 max-w-sm`} placeholder="Filter by action prefix, e.g. auth. or admin." value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter audit log" />
      <ErrorNote message={error} />
      {!rows ? (
        <Spinner />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Time</th>
                <th className="py-2 pr-3 font-medium">Action</th>
                <th className="py-2 pr-3 font-medium">User</th>
                <th className="py-2 pr-3 font-medium">Target</th>
                <th className="py-2 pr-3 font-medium">IP</th>
                <th className="py-2 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono text-xs">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="py-2 pr-3 font-sans text-muted">{fmtDate(r.created_at)}</td>
                  <td className="py-2 pr-3">{r.action}</td>
                  <td className="py-2 pr-3">{r.user_id ?? "—"}</td>
                  <td className="py-2 pr-3">{r.target ?? "—"}</td>
                  <td className="py-2 pr-3">{r.ip ?? "—"}</td>
                  <td className="max-w-xs truncate py-2" title={r.detail ? JSON.stringify(r.detail) : ""}>
                    {r.detail ? JSON.stringify(r.detail) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
