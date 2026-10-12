"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Card, ErrorNote, Pill, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { prettify } from "@/lib/format";

interface Integration {
  id: string;
  name: string;
  category: string;
  status: "operational" | "limited" | "requires_credentials" | "planned";
  detail: string;
}

const TONE = { operational: "ok", limited: "warn", requires_credentials: "unc", planned: "accent" } as const;
const ORDER = ["core", "social", "alerts", "identity", "enterprise"];

export default function IntegrationsPage() {
  const [items, setItems] = useState<Integration[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Integration[]>("/integrations").then(setItems).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <PageHeader
        title="Integrations"
        subtitle="What's live, what needs credentials, and what's planned. DeepShield only uses official APIs and authorized access, and never bypasses logins, CAPTCHAs or private-account settings."
      />
      <ErrorNote message={error} />
      {!items ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          {ORDER.filter((c) => items.some((i) => i.category === c)).map((cat) => (
            <Card key={cat} title={<span className="capitalize">{cat}</span>}>
              <ul className="grid gap-3 md:grid-cols-2">
                {items
                  .filter((i) => i.category === cat)
                  .map((i) => (
                    <li key={i.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{i.name}</span>
                        <Pill tone={TONE[i.status]}>{prettify(i.status)}</Pill>
                      </div>
                      <p className="mt-1.5 text-sm text-muted">{i.detail}</p>
                    </li>
                  ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
