"use client";

import {
  Activity,
  Bell,
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
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, auth, type User } from "@/lib/api";
import { cx } from "./ui";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/scan", label: "Scan content", icon: ScanSearch },
  { href: "/history", label: "History", icon: History },
  { href: "/cases", label: "Investigations", icon: FolderKanban },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/system", label: "System health", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

const UserCtx = createContext<{ user: User | null; refresh: () => void }>({ user: null, refresh: () => {} });
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

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [newAlerts, setNewAlerts] = useState(0);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(() => {
    api<User>("/auth/me").then(setUser).catch(() => {});
    api<{ id: number }[]>("/alerts?state=new").then((a) => setNewAlerts(a.length)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!auth.get()) {
      router.replace("/login");
      return;
    }
    refresh();
  }, [router, refresh]);

  useEffect(() => setOpen(false), [path]);

  const logout = () => {
    auth.clear();
    router.replace("/login");
  };

  const nav = (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-1">
      {NAV.map(({ href, label, icon: Icon }) => {
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
    <UserCtx.Provider value={{ user, refresh }}>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-panel focus:p-2">
        Skip to content
      </a>
      <div className="grid-bg min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
        <aside className="hidden border-r border-border bg-panel lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:gap-6 lg:p-4">
          <Logo />
          {nav}
          <div className="border-t border-border pt-3 text-xs text-muted">
            <p className="truncate" title={user?.email}>{user?.email}</p>
            <p className="capitalize">{user?.role}</p>
          </div>
        </aside>

        {open && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
            <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
            <div className="absolute inset-y-0 left-0 flex w-72 flex-col gap-6 bg-panel p-4">
              <div className="flex items-center justify-between">
                <Logo />
                <button onClick={() => setOpen(false)} aria-label="Close navigation" className="rounded p-2 text-muted">
                  <X className="h-5 w-5" />
                </button>
              </div>
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
            <Link href="/scan" className="hidden rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast sm:inline-flex">
              Scan content
            </Link>
            <ThemeToggle />
            <button onClick={logout} className="rounded-lg p-2 text-muted hover:bg-panel-2 hover:text-text" aria-label="Sign out">
              <LogOut className="h-5 w-5" />
            </button>
          </header>
          <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
            {children}
          </main>
          <footer className="px-6 py-4 text-center text-xs text-muted">
            DeepShield AI gives probabilistic estimates, not proof. ·{" "}
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
