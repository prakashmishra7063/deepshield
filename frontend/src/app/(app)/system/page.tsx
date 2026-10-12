"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Card, ErrorNote, Pill, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

interface Health {
  status: string;
  pipeline_version: string;
  queue_depth: number;
  ffmpeg: boolean;
  models_configured: boolean;
  detectors: { name: string; version: string; kinds: string[]; category: string; description: string; available: boolean; reason: string | null }[];
}

export default function SystemPage() {
  const [h, setH] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Health>("/system/health").then(setH).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <PageHeader title="System health & models" subtitle="Detectors that aren't available are skipped and listed in every report's limitations. They never return placeholder results." />
      <ErrorNote message={error} />
      {!h ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[
              ["API", h.status === "ok" ? "Operational" : h.status],
              ["Pipeline", `v${h.pipeline_version}`],
              ["Queue depth", String(h.queue_depth)],
              ["ffmpeg", h.ffmpeg ? "Installed" : "Not installed"],
            ].map(([k, v]) => (
              <div key={k} className="rounded-xl border border-border bg-panel p-4">
                <p className="text-sm text-muted">{k}</p>
                <p className="mt-1 text-lg font-semibold">{v}</p>
              </div>
            ))}
          </div>
          <Card title="Detectors">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th className="py-2 pr-3 font-medium">Detector</th>
                    <th className="py-2 pr-3 font-medium">Class</th>
                    <th className="py-2 pr-3 font-medium">Media</th>
                    <th className="py-2 pr-3 font-medium">Status</th>
                    <th className="py-2 font-medium">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {h.detectors.map((d) => (
                    <tr key={d.name}>
                      <td className="py-2.5 pr-3 font-mono text-xs">
                        {d.name} <span className="text-muted">v{d.version}</span>
                      </td>
                      <td className="py-2.5 pr-3">{d.category}</td>
                      <td className="py-2.5 pr-3 text-xs">{d.kinds.join(", ")}</td>
                      <td className="py-2.5 pr-3">
                        <Pill tone={d.available ? "ok" : "unc"}>{d.available ? "available" : "unavailable"}</Pill>
                      </td>
                      <td className="py-2.5 text-xs text-muted">
                        {d.description}
                        {d.reason && <span className="mt-0.5 block text-warn">{d.reason}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
