"use client";

import { Copy, KeyRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeader, useUser } from "@/components/AppShell";
import { Button, Card, ErrorNote, Field, Pill, inputCls } from "@/components/ui";
import { api, auth, type ApiToken, type User } from "@/lib/api";
import { fmtDate } from "@/lib/format";

export default function SettingsPage() {
  const { user, refresh } = useUser();
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [name, setName] = useState("Browser extension");
  const [fresh, setFresh] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const loadTokens = () => api<ApiToken[]>("/auth/tokens").then(setTokens).catch((e) => setError(e.message));
  useEffect(() => {
    loadTokens();
  }, []);

  const save = async (patch: Partial<User>) => {
    setSaved(false);
    try {
      await api("/auth/me/settings", { method: "PATCH", json: patch });
      refresh();
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const t = await api<ApiToken>("/auth/tokens", { method: "POST", json: { name } });
      setFresh(t.token ?? null);
      loadTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create token");
    }
  };

  const revoke = async (id: number) => {
    if (!confirm("Revoke this token? Anything using it stops working immediately.")) return;
    await api(`/auth/tokens/${id}`, { method: "DELETE" });
    loadTokens();
  };

  return (
    <>
      <PageHeader title="Settings" subtitle={user ? `Signed in as ${user.email} (${user.role})` : undefined} />
      <ErrorNote message={error} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Alert preferences">
          {user && (
            <div className="space-y-4">
              <Field label="Raise an alert when a result is at least" hint="Alerts appear in-app. Email requires SMTP to be configured by your administrator.">
                <select className={inputCls} value={user.alert_threshold} onChange={(e) => save({ alert_threshold: e.target.value })}>
                  <option value="potentially_manipulated">Potentially Manipulated</option>
                  <option value="high_risk">High Risk — Possible Deepfake</option>
                </select>
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={user.email_alerts} onChange={(e) => save({ email_alerts: e.target.checked })} />
                Also send email alerts
              </label>
              {saved && (
                <p className="text-xs text-ok" role="status">
                  Saved.
                </p>
              )}
            </div>
          )}
        </Card>

        <Card title="API tokens (browser extension)">
          <form onSubmit={create} className="mb-4 flex gap-2">
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} aria-label="Token name" required maxLength={100} />
            <Button type="submit">
              <KeyRound className="h-4 w-4" aria-hidden /> Create
            </Button>
          </form>
          {fresh && (
            <div className="mb-4 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm">
              <p className="font-medium text-warn">Copy this token now. It won&apos;t be shown again.</p>
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-panel-2 px-2 py-1 font-mono text-xs">{fresh}</code>
                <Button variant="secondary" onClick={() => navigator.clipboard.writeText(fresh)} aria-label="Copy token">
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
          <ul className="divide-y divide-border">
            {tokens.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="font-medium">{t.name}</span>
                <code className="font-mono text-xs text-muted">{t.prefix}…</code>
                <span className="flex-1 text-xs text-muted">last used {t.last_used_at ? fmtDate(t.last_used_at) : "never"}</span>
                {t.revoked ? (
                  <Pill>revoked</Pill>
                ) : (
                  <Button variant="ghost" onClick={() => revoke(t.id)}>
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <AccountSecurity />
    </>
  );
}

function AccountSecurity() {
  const { user } = useUser();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [delPw, setDelPw] = useState("");
  const [delText, setDelText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const change = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    try {
      const r = await api<{ access_token: string }>("/auth/change-password", {
        method: "POST",
        json: { current_password: cur, new_password: next },
      });
      auth.set(r.access_token);
      setCur("");
      setNext("");
      setMsg("Password changed. Other sessions were signed out.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password");
    }
  };

  const everywhere = async () => {
    if (!confirm("Sign out of every browser and device, including this one?")) return;
    await api("/auth/logout-everywhere", { method: "POST" });
    auth.clear();
    window.location.assign("/login");
  };

  const remove = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/me", { method: "DELETE", json: { password: delPw, confirm: delText } });
      auth.clear();
      window.location.assign("/register");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete account");
    }
  };

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <Card title="Password & sessions">
        <form onSubmit={change} className="space-y-3">
          <Field label="Current password">
            <input className={inputCls} type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required />
          </Field>
          <Field label="New password" hint="At least 10 characters.">
            <input className={inputCls} type="password" autoComplete="new-password" minLength={10} value={next} onChange={(e) => setNext(e.target.value)} required />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button type="submit">Change password</Button>
            <Button type="button" variant="secondary" onClick={everywhere}>
              Sign out everywhere
            </Button>
          </div>
        </form>
        {msg && (
          <p className="mt-3 text-xs text-ok" role="status">
            {msg}
          </p>
        )}
      </Card>
      <Card title="Delete account">
        <form onSubmit={remove} className="space-y-3">
          <p className="text-sm text-muted">
            Permanently deletes your account and your personal workspace, including its scans, evidence and stored
            media. Team workspaces keep the work you contributed. This can&apos;t be undone.
          </p>
          <Field label="Password">
            <input className={inputCls} type="password" autoComplete="current-password" value={delPw} onChange={(e) => setDelPw(e.target.value)} required />
          </Field>
          <Field label='Type "DELETE" to confirm'>
            <input className={inputCls} value={delText} onChange={(e) => setDelText(e.target.value)} required />
          </Field>
          <Button type="submit" variant="danger" disabled={delText !== "DELETE" || user?.role === "owner"}>
            Delete my account
          </Button>
          {user?.role === "owner" && <p className="text-xs text-muted">Platform owners must hand ownership to another user first.</p>}
        </form>
      </Card>
      <div className="lg:col-span-2">
        <ErrorNote message={error} />
      </div>
    </div>
  );
}
