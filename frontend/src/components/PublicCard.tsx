"use client";

import type { ReactNode } from "react";
import { Logo, ThemeToggle } from "./AppShell";

/** Centered card layout for public account pages (verify, reset, invite). */
export default function PublicCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid-bg flex min-h-screen flex-col p-6">
      <div className="flex items-center justify-between">
        <Logo />
        <ThemeToggle />
      </div>
      <main className="m-auto w-full max-w-md rounded-2xl border border-border bg-panel p-8 shadow-sm">
        <h1 className="text-xl font-semibold">{title}</h1>
        <div className="mt-4 space-y-4 text-sm">{children}</div>
      </main>
    </div>
  );
}
