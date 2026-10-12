"use client";

import {
  Activity,
  Bell,
  Building2,
  ChevronsUpDown,
  Crown,
  FolderKanban,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Plug,
  ScanSearch,
  Settings,
  Shield,
  Sun,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, auth, type Org, type User } from "@/lib/api";
import { cx } from "./ui";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/scan", label: "Scan content", icon: ScanSearch },
  { href: "/history", label: "History", icon: History },
  { href: "/cases", label: "Investigations", icon: FolderKanban },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/team", label: "Workspace & plan", icon: Users },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/system", label: "System health", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface UserCtxValue {
  user: User | null;
  org: Org | null;
  refresh: () => void;
}
const UserCtx = createContext<UserCtxValue>({ user: null, org: null, refresh: () => {} });
export const useUser = () => useContext(UserCtx);

export function ThemeToggle() {
  const [dark, setDark] = useState(true);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("ds_theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  };
  return (
    <button onClick={toggle} className="rounded-lg p-2 text-muted hover:bg-panel-2 hover:text-text" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>
      {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  );
}

export function Logo() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 text-accent">
        <Shield className="h-5 w-5" aria-hidden />
      </span>
      <span>
        DeepShield <span className="text-accent">AI</span>
      </span>
    </Link>
  );
}

function WorkspaceSwitcher({ user, org, onSwitch }: { user: User; org: Org | null; onSwitch: () => void }) {
  const [open, setOpen] = useState(false);
  const switchTo = async (id: number) => {
    setOpen(false);
    if (id === user.active_org_id) return;
    await api("/auth/switch-org", { method: "POST", json: { org_id: id } });
    onSwitch();
    window.location.assign("/dashboard");
  };
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="Switch workspace"
        className="flex w-full items-center gap-2 rounded-lg border border-border bg-panel-2 px-3 py-2 text-left text-sm hover:border-accent"
      >
        <Building2 className="h-4 w-4 shrink-0 text-accent" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{org?.name ?? "Workspace"}</span>
          <span className="block text-xs text-muted">{org ? `${org.plan.name} plan · ${org.kind}` : "…"}</span>
        </span>
        <ChevronsUpDown className="h-4 w-4 text-muted" aria-hidden />
      </button>
      {open && (
        <div className="absolute inset-x-0 z-40 mt-1 rounded-lg border border-border bg-panel p-1 shadow-xl" role="menu">
          {user.memberships.map((m) => (
            <button
              key={m.org_id}
              role="menuitem"
              onClick={() => switchTo(m.org_id)}
              className={cx("block w-full truncate rounded-md px-3 py-1.5 text-left text-sm hover:bg-panel-2", m.org_id === user.active_org_id && "text-accent")}
            >
              {m.name} <span className="text-xs text-muted">· {m.role}</span>
            </button>
          ))}
          <Link href="/team?new=1" onClick={() => setOpen(false)} className="block rounded-md px-3 py-1.5 text-sm text-accent hover:bg-panel-2">
            + Create team workspace
          </Link>
        </div>
      )}
    </div>
  );
}

function Banners({ user, org }: { user: User; org: Org | null }) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const resend = async () => {
    setState("sending");
    setError(null);
    try {
      await api("/auth/resend-verification", { method: "POST" });
      setState("sent");
    } catch (e) {
      setState("error");
      setError(e instanceof Error ? e.message : "The email could not be sent");
    }
  };
  const out = [];
  if (!user.email_verified && user.require_email_verification) {
    const realEmail = user.email_delivery === "smtp";
    out.push(
      <div key="verify" className="flex flex-wrap items-center gap-3 border-b border-warn/30 bg-warn/10 px-6 py-2.5 text-sm">
        <span className="flex-1">
          {realEmail ? (
            <>
              Verify your email address ({user.email}) to start scanning. Check your inbox and spam folder for the
              link.
            </>
          ) : user.role === "owner" ? (
            <>Email delivery isn&apos;t set up on this server, so verification emails aren&apos;t reaching inboxes. See Owner console → Settings.</>
          ) : (
            <>
              Verify your email address ({user.email}) to start scanning. This server can&apos;t send email yet, so
              ask the administrator to verify your account.
            </>
          )}
          {error && <span className="mt-1 block text-danger">{error}</span>}
        </span>
        {realEmail && (
          <button onClick={resend} disabled={state === "sending" || state === "sent"} className="font-medium text-warn underline disabled:no-underline">
            {state === "sending" ? "Sending…" : state === "sent" ? "Email sent" : "Resend email"}
          </button>
        )}
      </div>,
    );
  }
  if (org?.status === "suspended") {
    out.push(
      <div key="susp" className="border-b border-danger/30 bg-danger/10 px-6 py-2.5 text-sm text-danger">
        This workspace is suspended. Existing results are viewable, but new scans are disabled. Contact support.
      </div>,
    );
  } else if (org && org.usage.limit >= 0 && org.usage.used >= org.usage.limit && org.usage.credits <= 0) {
    out.push(
      <div key="quota" className="flex flex-wrap items-center gap-3 border-b border-warn/30 bg-warn/10 px-6 py-2.5 text-sm">
        <span className="flex-1">You&apos;ve used all {org.usage.limit} scans in your {org.plan.name} plan this month.</span>
        <Link href="/team" className="font-medium text-warn underline">
          See plans
        </Link>
      </div>,
    );
  }
  return <>{out}</>;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [org, setOrg] = useState<Org | null>(null);
  const [newAlerts, setNewAlerts] = useState(0);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(() => {
    api<User>("/auth/me").then(setUser).catch(() => {});
    api<Org>("/org").then(setOrg).catch(() => {});
    api<{ id: number }[]>("/alerts?state=new").then((a) => setNewAlerts(a.length)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!auth.get()) {
      router.replace(`/login?next=${encodeURIComponent(path)}`);
      return;
    }
    refresh();
  }, [router, refresh, path]);

  useEffect(() => setOpen(false), [path]);

  const logout = () => {
    auth.clear();
    router.replace("/login");
  };

  const items = user?.role === "owner" ? [...NAV, { href: "/admin", label: "Owner console", icon: Crown }] : NAV;

  const nav = (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-1">
      {items.map(({ href, label, icon: Icon }) => {
        const active = path === href || (href !== "/dashboard" && path.startsWith(href));
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
              active ? "bg-accent/12 font-medium text-accent" : "text-muted hover:bg-panel-2 hover:text-text",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            <span className="flex-1">{label}</span>
            {href === "/alerts" && newAlerts > 0 && (
              <span className="rounded-full bg-danger px-1.5 text-xs font-semibold text-white" aria-label={`${newAlerts} new alerts`}>
                {newAlerts}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <UserCtx.Provider value={{ user, org, refresh }}>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-panel focus:p-2">
        Skip to content
      </a>
      <div className="grid-bg min-h-screen lg:grid lg:grid-cols-[256px_1fr]">
        <aside className="hidden border-r border-border bg-panel lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:gap-5 lg:p-4">
          <Logo />
          {user && <WorkspaceSwitcher user={user} org={org} onSwitch={refresh} />}
          {nav}
          <div className="border-t border-border pt-3 text-xs text-muted">
            <p className="truncate" title={user?.email}>
              {user?.email}
            </p>
            <p>{user?.role === "owner" ? "Platform owner" : org ? `Workspace ${org.my_role}` : ""}</p>
          </div>
        </aside>

        {open && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
            <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
            <div className="absolute inset-y-0 left-0 flex w-72 flex-col gap-5 overflow-y-auto bg-panel p-4">
              <div className="flex items-center justify-between">
                <Logo />
                <button onClick={() => setOpen(false)} aria-label="Close navigation" className="rounded p-2 text-muted">
                  <X className="h-5 w-5" />
                </button>
              </div>
              {user && <WorkspaceSwitcher user={user} org={org} onSwitch={refresh} />}
              {nav}
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-col">
          <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-bg/85 px-4 py-3 backdrop-blur sm:px-6">
            <button className="rounded-lg p-2 text-muted lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
              <Menu className="h-5 w-5" />
            </button>
            <div className="lg:hidden">
              <Logo />
            </div>
            <div className="flex-1" />
            {org && org.usage.limit >= 0 && (
              <Link href="/team" className="hidden text-xs text-muted hover:text-text md:block" title="Scans used this month">
                {org.usage.used}/{org.usage.limit} scans{org.usage.credits > 0 ? ` · ${org.usage.credits} credits` : ""}
              </Link>
            )}
            <Link href="/scan" className="hidden rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast sm:inline-flex">
              Scan content
            </Link>
            <ThemeToggle />
            <button onClick={logout} className="rounded-lg p-2 text-muted hover:bg-panel-2 hover:text-text" aria-label="Sign out">
              <LogOut className="h-5 w-5" />
            </button>
          </header>
          {user && <Banners user={user} org={org} />}
          <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
            {children}
          </main>
          <footer className="px-6 py-4 text-center text-xs text-muted">
            DeepShield AI gives probabilistic estimates, not proof. ·{" "}
            <Link href="/pricing" className="underline">
              Pricing
            </Link>{" "}
            ·{" "}
            <Link href="/responsible-use" className="underline">
              Privacy &amp; responsible use
            </Link>
          </footer>
        </div>
      </div>
    </UserCtx.Provider>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
