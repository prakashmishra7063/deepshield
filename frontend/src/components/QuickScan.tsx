"use client";

import { Link2, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { api, uploadFile, type Analysis } from "@/lib/api";
import { fmtBytes } from "@/lib/format";
import { Button, Card, ErrorNote, Progress, cx, inputCls } from "./ui";

const ACCEPT = "image/jpeg,image/png,image/webp,image/gif,image/bmp,image/tiff,video/mp4,video/quicktime,video/webm,video/x-msvideo,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/ogg,audio/flac";
const MAX_MB = 100;

export default function QuickScan({ large = false }: { large?: boolean }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [url, setUrl] = useState("");
  const [pct, setPct] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (f: File) => {
    setError(null);
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`That file is ${fmtBytes(f.size)}. The upload limit is ${MAX_MB} MB.`);
      return;
    }
    setFile(f);
    setPct(0);
    try {
      const a = await uploadFile(f, setPct);
      router.push(`/analyses/${a.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      setPct(null);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) send(f);
  };

  const scanUrl = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const a = await api<Analysis>("/analyses/url", { method: "POST", json: { url: url.trim() } });
      router.push(`/analyses/${a.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the scan");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Scan content">
      <div className={cx("grid gap-4", large ? "lg:grid-cols-1" : "lg:grid-cols-2")}>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          className={cx(
            "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition",
            large && "min-h-64",
            drag ? "border-accent bg-accent/8" : "border-border",
          )}
        >
          <UploadCloud className="h-8 w-8 text-accent" aria-hidden />
          <p className="text-sm font-medium">Drag and drop an image, video or audio file</p>
          <p className="text-xs text-muted">JPG, PNG, WEBP, MP4, MOV, WEBM, WAV, MP3 and more · up to {MAX_MB} MB</p>
          <Button variant="secondary" onClick={() => input.current?.click()} disabled={pct !== null}>
            Choose file
          </Button>
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            aria-label="Choose a file to analyze"
            onChange={(e) => e.target.files?.[0] && send(e.target.files[0])}
          />
          {pct !== null && file && (
            <div className="mt-2 w-full max-w-xs text-left">
              <p className="mb-1 truncate text-xs text-muted">
                Uploading {file.name} · {pct}%
              </p>
              <Progress value={pct} label="Upload progress" />
            </div>
          )}
        </div>

        <form onSubmit={scanUrl} className="flex flex-col justify-center gap-3 rounded-xl border border-border bg-panel-2/50 p-6">
          <label htmlFor="scan-url" className="flex items-center gap-2 text-sm font-medium">
            <Link2 className="h-4 w-4 text-accent" aria-hidden /> Paste a public URL
          </label>
          <input
            id="scan-url"
            className={inputCls}
            type="url"
            required
            placeholder="https://example.com/photo.jpg or a web page"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <p className="text-xs text-muted">
            Direct media links and public web pages are supported. Social platforms that require login or official API
            access are reported as such and are never scraped around access controls.
          </p>
          <Button type="submit" loading={busy} className="self-start">
            Analyze URL
          </Button>
        </form>
      </div>
      <div className="mt-3">
        <ErrorNote message={error} />
      </div>
    </Card>
  );
}
