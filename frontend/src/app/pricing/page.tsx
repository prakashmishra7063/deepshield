"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Logo, ThemeToggle } from "@/components/AppShell";
import PlanCards from "@/components/PlanCards";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, type Plan } from "@/lib/api";

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Plan[]>("/plans").then(setPlans).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="grid-bg min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between p-6">
        <Logo />
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <Link href="/login" className="text-sm">
            Sign in
          </Link>
          <Link href="/register" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast">
            Start free
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 pb-16">
        <h1 className="mt-6 text-center text-4xl font-semibold tracking-tight">
          See Beyond the Fake. <span className="text-accent">Protect What&apos;s Real.</span>
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-center text-muted">
          Check images, video, audio and web pages for signs of manipulation, AI generation and impersonation, with the
          evidence behind every result.
        </p>
        <div className="mt-10">
          <ErrorNote message={error} />
          {!plans ? <Spinner /> : <PlanCards plans={plans} action={() => (
            <Link href="/register" className="block rounded-lg bg-accent px-4 py-2 text-center text-sm font-medium text-accent-contrast">
              Get started
            </Link>
          )} />}
        </div>
        <p className="mt-8 text-center text-xs text-muted">
          Need more scans? Scan credits can be added to any plan. Results are probabilistic estimates, not proof.{" "}
          <Link href="/responsible-use" className="underline">
            Privacy &amp; responsible use
          </Link>
        </p>
      </main>
    </div>
  );
}
