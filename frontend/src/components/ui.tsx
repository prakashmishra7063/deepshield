"use client";

import { AlertTriangle, CheckCircle2, HelpCircle, Loader2, ShieldAlert } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Classification } from "@/lib/api";
import { CLASS_META } from "@/lib/format";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Card({ children, className, title, action }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={cx("rounded-xl border border-border bg-panel p-5 shadow-sm", className)}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold tracking-wide text-text">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
export function Button({ variant = "primary", className, loading, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: "bg-accent text-accent-contrast hover:opacity-90",
    secondary: "border border-border bg-panel-2 text-text hover:border-accent",
    ghost: "text-muted hover:bg-panel-2 hover:text-text",
    danger: "border border-danger/40 text-danger hover:bg-danger/10",
  };
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

const TONE: Record<string, string> = {
  ok: "bg-ok/12 text-ok border-ok/30",
  unc: "bg-unc/12 text-unc border-unc/30",
  warn: "bg-warn/12 text-warn border-warn/30",
  danger: "bg-danger/12 text-danger border-danger/30",
  accent: "bg-accent/12 text-accent border-accent/30",
};

export function Pill({ tone = "unc", children, className }: { tone?: string; children: ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", TONE[tone], className)}>{children}</span>;
}

const ICON: Record<Classification, typeof CheckCircle2> = {
  likely_authentic: CheckCircle2,
  uncertain: HelpCircle,
  potentially_manipulated: AlertTriangle,
  high_risk: ShieldAlert,
};

export function ClassBadge({ value, size = "sm" }: { value: Classification | null; size?: "sm" | "lg" }) {
  if (!value) return <Pill>—</Pill>;
  const meta = CLASS_META[value];
  const Icon = ICON[value];
  if (size === "lg") {
    return (
      <div className={cx("inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-base font-semibold", TONE[meta.tone])}>
        <Icon className="h-5 w-5" aria-hidden />
        {meta.label}
      </div>
    );
  }
  return (
    <Pill tone={meta.tone}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {meta.short}
    </Pill>
  );
}

export function StatusPill({ status }: { status: string }) {
  const tone = status === "completed" ? "ok" : status === "failed" ? "danger" : "accent";
  return (
    <Pill tone={tone}>
      {(status === "queued" || status === "running") && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {status}
    </Pill>
  );
}

export function Progress({ value, label }: { value: number; label?: string }) {
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-panel-2" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label={label ?? "Progress"}>
        <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.max(2, value)}%` }} />
      </div>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-8 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
      {message}
    </p>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls =
  "w-full rounded-lg border border-border bg-panel-2 px-3 py-2 text-sm text-text placeholder:text-muted focus:border-accent focus:outline-none";
