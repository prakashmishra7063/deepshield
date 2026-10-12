"use client";

import { Copy, KeyRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeader, useUser } from "@/components/AppShell";
import { Button, Card, ErrorNote, Field, Pill, inputCls } from "@/components/ui";
import { api, type ApiToken, type User } from "@/lib/api";
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
    </>
  );
}
