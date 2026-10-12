"use client";

import { Check } from "lucide-react";
import type { ReactNode } from "react";
import type { Plan } from "@/lib/api";
import { fmtMoney, fmtScans } from "@/lib/format";
import { cx } from "./ui";

export default function PlanCards({ plans, current, action }: { plans: Plan[]; current?: string; action?: (p: Plan) => ReactNode }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {plans.map((p) => (
        <div key={p.id} className={cx("flex flex-col rounded-xl border bg-panel p-5", p.id === current ? "border-accent" : "border-border")}>
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">{p.name}</h3>
            {p.id === current && <span className="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent">Current</span>}
          </div>
          <p className="mt-1 text-sm text-muted">{p.description}</p>
          <p className="mt-4 text-3xl font-semibold">
            {fmtMoney(p.price_monthly_cents, p.currency)}
            {p.price_monthly_cents > 0 && <span className="text-sm font-normal text-muted"> / month</span>}
          </p>
          <ul className="mt-4 flex-1 space-y-2 text-sm">
            {[fmtScans(p.monthly_scans), `Files up to ${p.max_upload_mb} MB`, p.max_members > 1 ? `Up to ${p.max_members} team members` : "Single user", "PDF & JSON evidence reports", "Browser extension"].map((f) => (
              <li key={f} className="flex items-center gap-2">
                <Check className="h-4 w-4 text-ok" aria-hidden /> {f}
              </li>
            ))}
          </ul>
          {action && <div className="mt-5">{action(p)}</div>}
        </div>
      ))}
    </div>
  );
}
