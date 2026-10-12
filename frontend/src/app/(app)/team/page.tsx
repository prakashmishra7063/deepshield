"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { PageHeader, useUser } from "@/components/AppShell";
import PlanCards from "@/components/PlanCards";
import { Button, Card, ErrorNote, Field, Pill, Progress, Spinner, inputCls } from "@/components/ui";
import { api, type Org, type Plan } from "@/lib/api";
import { fmtDate } from "@/lib/format";

function UsageCard({ org }: { org: Org }) {
  const u = org.usage;
  const unlimited = u.limit < 0;
  const pct = unlimited ? 0 : Math.min(100, Math.round((u.used / Math.max(1, u.limit)) * 100));
  return (
    <Card title="This month's usage">
      <p className="text-3xl font-semibold tabular-nums">
        {u.used}
        <span className="text-base font-normal text-muted"> / {unlimited ? "unlimited" : u.limit} scans</span>
      </p>
      {!unlimited && (
        <div className="mt-3">
          <Progress value={pct} label="Scans used this month" />
        </div>
      )}
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-panel-2 p-3">
          <dt className="text-xs text-muted">Extra scan credits</dt>
          <dd className="mt-0.5 font-medium">{u.credits}</dd>
        </div>
        <div className="rounded-lg bg-panel-2 p-3">
          <dt className="text-xs text-muted">Seats</dt>
          <dd className="mt-0.5 font-medium">
            {org.seats_used} / {org.plan.max_members}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-muted">
        Resets on the 1st of each month (UTC). Credits are used only after the plan&apos;s monthly scans run out, and
        media found on scanned pages is never counted.
      </p>
    </Card>
  );
}

function TeamInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, refresh } = useUser();
  const [org, setOrg] = useState<Org | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [teamName, setTeamName] = useState("");
  const [name, setName] = useState("");

  const load = () =>
    api<Org>("/org")
      .then((o) => {
        setOrg(o);
        setName(o.name);
      })
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
    api<Plan[]>("/plans").then(setPlans).catch(() => {});
  }, []);

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setError(null);
    setNotice(null);
    try {
      await fn();
      if (ok) setNotice(ok);
      await load();
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  };

  const createTeam = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api("/orgs", { method: "POST", json: { name: teamName } });
      setTeamName("");
    }, "Team workspace created. You're now working in it.");
  };

  const sendInvite = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api("/org/invites", { method: "POST", json: { email: inviteEmail, role: inviteRole } });
      setInviteEmail("");
    }, `Invitation sent to ${inviteEmail}.`);
  };

  if (!org) return error ? <ErrorNote message={error} /> : <Spinner />;
  const admin = org.my_role === "owner" || org.my_role === "admin";

  return (
    <>
      <PageHeader title="Workspace & plan" subtitle={`${org.name} · ${org.kind === "team" ? "Team workspace" : "Personal workspace"} · you are ${org.my_role}`} />
      <div className="space-y-6">
        <ErrorNote message={error} />
        {notice && (
          <p role="status" className="rounded-lg border border-ok/30 bg-ok/10 px-3 py-2 text-sm text-ok">
            {notice}
          </p>
        )}
        {org.status === "suspended" && <ErrorNote message="This workspace is suspended. Contact support." />}

        <div className="grid gap-6 lg:grid-cols-2">
          <UsageCard org={org} />
          <Card title="Workspace">
            {admin ? (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(() => api("/org", { method: "PATCH", json: { name } }), "Workspace renamed.");
                }}
              >
                <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} aria-label="Workspace name" minLength={2} maxLength={120} required />
                <Button type="submit" variant="secondary">
                  Rename
                </Button>
              </form>
            ) : (
              <p className="font-medium">{org.name}</p>
            )}
            <form onSubmit={createTeam} className="mt-6 space-y-2" id="new-team">
              <Field label="Create a team workspace" hint="For businesses: invite colleagues and share scans and investigations. You'll be its owner.">
                <div className="flex gap-2">
                  <input className={inputCls} placeholder="e.g. Acme Trust & Safety" value={teamName} onChange={(e) => setTeamName(e.target.value)} minLength={2} maxLength={120} required autoFocus={params.get("new") === "1"} />
                  <Button type="submit">Create</Button>
                </div>
              </Field>
            </form>
            {org.kind === "team" && user && (
              <Button
                variant="danger"
                className="mt-6"
                onClick={() =>
                  confirm(`Leave "${org.name}"? You'll lose access to its scans and investigations.`) &&
                  run(async () => {
                    await api(`/org/members/${user.id}`, { method: "DELETE" });
                    router.replace("/dashboard");
                  })
                }
              >
                Leave workspace
              </Button>
            )}
          </Card>
        </div>

        {org.kind === "team" && (
          <Card title={`Members (${org.members.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th className="py-2 pr-3 font-medium">Email</th>
                    <th className="py-2 pr-3 font-medium">Role</th>
                    <th className="py-2 pr-3 font-medium">Joined</th>
                    <th className="py-2 font-medium" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {org.members.map((m) => (
                    <tr key={m.user_id}>
                      <td className="py-2.5 pr-3">
                        {m.email}
                        {m.user_id === user?.id && <span className="text-muted"> (you)</span>}
                      </td>
                      <td className="py-2.5 pr-3">
                        {admin && m.user_id !== user?.id ? (
                          <select
                            className={`${inputCls} w-auto py-1`}
                            value={m.role}
                            aria-label={`Role for ${m.email}`}
                            onChange={(e) => run(() => api(`/org/members/${m.user_id}`, { method: "PATCH", json: { role: e.target.value } }), "Role updated.")}
                          >
                            <option value="member">member</option>
                            <option value="admin">admin</option>
                            {org.my_role === "owner" && <option value="owner">owner</option>}
                          </select>
                        ) : (
                          <Pill>{m.role}</Pill>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-muted">{fmtDate(m.joined_at)}</td>
                      <td className="py-2.5 text-right">
                        {admin && m.user_id !== user?.id && (
                          <Button
                            variant="ghost"
                            onClick={() => confirm(`Remove ${m.email} from this workspace?`) && run(() => api(`/org/members/${m.user_id}`, { method: "DELETE" }), "Member removed.")}
                          >
                            Remove
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {admin && (
              <div className="mt-6 border-t border-border pt-4">
                <form onSubmit={sendInvite} className="flex flex-wrap gap-2">
                  <input className={`${inputCls} max-w-xs flex-1`} type="email" placeholder="colleague@company.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} required aria-label="Email to invite" />
                  <select className={`${inputCls} w-auto`} value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} aria-label="Role">
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                  <Button type="submit">Send invite</Button>
                </form>
                {org.invites.length > 0 && (
                  <ul className="mt-4 space-y-1 text-sm">
                    {org.invites.map((i) => (
                      <li key={i.id} className="flex flex-wrap items-center gap-2">
                        <span>{i.email}</span>
                        <Pill>{i.role}</Pill>
                        <span className="flex-1 text-xs text-muted">pending · expires {fmtDate(i.expires_at)}</span>
                        <Button variant="ghost" onClick={() => run(() => api(`/org/invites/${i.id}`, { method: "DELETE" }), "Invitation cancelled.")}>
                          Cancel
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Card>
        )}

        <div>
          <h2 className="mb-3 text-sm font-semibold">Plans</h2>
          <PlanCards
            plans={plans}
            current={org.plan.id}
            action={(p) =>
              p.id === org.plan.id ? null : (
                <p className="text-xs text-muted">
                  Online payment is being set up. To switch to {p.name} or buy scan credits now, contact support.
                </p>
              )
            }
          />
        </div>
      </div>
    </>
  );
}

export default function TeamPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <TeamInner />
    </Suspense>
  );
}
