"use client";

import { useEffect, useState } from "react";
import { evidenceUrl, type EvidenceItem, type Signal } from "@/lib/api";
import { cx } from "./ui";

export function EvidenceImage({ analysisId, item, className }: { analysisId: string; item: EvidenceItem; className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    let live = true;
    evidenceUrl(analysisId, item.name)
      .then((u) => {
        url = u;
        if (live) setSrc(u);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [analysisId, item.name]);
  if (failed) return <div className="grid h-32 place-items-center rounded-lg bg-panel-2 text-xs text-muted">Evidence unavailable</div>;
  if (!src) return <div className={cx("h-32 animate-pulse rounded-lg bg-panel-2", className)} />;
  return <img src={src} alt={item.caption} className={cx("w-full rounded-lg border border-border object-contain", className)} />;
}

export function VideoTimeline({ analysisId, frames, signals, duration }: { analysisId: string; frames: EvidenceItem[]; signals: Signal[]; duration: number }) {
  const [sel, setSel] = useState(0);
  const flagged = signals.flatMap((s) => {
    const ts = (s.evidence?.timestamps_s as number[] | undefined) ?? (s.timestamp_s !== null ? [s.timestamp_s] : []);
    return ts.map((t) => ({ t, s }));
  });
  const total = duration || Math.max(1, ...frames.map((f) => f.timestamp_s ?? 0));
  const current = frames[sel];

  return (
    <div className="space-y-3">
      {current && <EvidenceImage analysisId={analysisId} item={current} className="max-h-[420px] bg-black" />}
      <p className="text-xs text-muted">{current?.caption}</p>
      <div className="relative h-8 rounded-md bg-panel-2" aria-label="Video timeline">
        {flagged.map(({ t, s }, i) => (
          <span
            key={i}
            title={`${s.title} at ${t}s`}
            className="absolute top-0 h-full w-1 -translate-x-1/2 rounded bg-warn"
            style={{ left: `${Math.min(100, (t / total) * 100)}%` }}
          />
        ))}
        {frames.map((f, i) => (
          <button
            key={f.name}
            onClick={() => setSel(i)}
            aria-label={`Show keyframe at ${f.timestamp_s}s`}
            aria-pressed={i === sel}
            className={cx(
              "absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2",
              i === sel ? "border-accent bg-accent" : "border-muted bg-panel hover:border-accent",
            )}
            style={{ left: `${Math.min(100, ((f.timestamp_s ?? 0) / total) * 100)}%` }}
          />
        ))}
      </div>
      <div className="flex justify-between text-xs text-muted">
        <span>0s</span>
        {flagged.length > 0 && <span className="text-warn">▮ flagged moments</span>}
        <span>{total.toFixed(1)}s</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {frames.map((f, i) => (
          <button key={f.name} onClick={() => setSel(i)} className={cx("w-24 shrink-0 rounded-lg border-2", i === sel ? "border-accent" : "border-transparent")}>
            <EvidenceImage analysisId={analysisId} item={f} className="h-14 object-cover" />
            <span className="block text-center text-[11px] text-muted">{f.timestamp_s}s</span>
          </button>
        ))}
      </div>
    </div>
  );
}
