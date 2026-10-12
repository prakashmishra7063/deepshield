"use client";

import { Eye, Fingerprint, ScanFace, Waves } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, auth } from "@/lib/api";
import { Logo, ThemeToggle } from "./AppShell";
import { Button, ErrorNote, Field, inputCls } from "./ui";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await api("/auth/register", { method: "POST", json: { email, password, accept_terms: terms } });
      }
      const t = await api<{ access_token: string }>("/auth/login", { method: "POST", json: { email, password } });
      auth.set(t.access_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid-bg grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-border bg-panel p-10 lg:flex">
        <Logo />
        <div>
          <h1 className="text-4xl font-semibold leading-tight tracking-tight">
            See Beyond the Fake.
            <br />
            <span className="text-accent">Protect What&apos;s Real.</span>
          </h1>
          <p className="mt-4 max-w-md text-muted">
            Analyze images, video, audio and web pages for signs of manipulation, AI generation and impersonation, with
            the evidence and the uncertainty laid out alongside every result.
          </p>
          <ul className="mt-8 grid max-w-md gap-3 text-sm">
            {[
              [ScanFace, "Image & video forensics with keyframe timeline"],
              [Waves, "Audio spectral analysis for synthetic-voice clues"],
              [Fingerprint, "C2PA Content Credentials verification"],
              [Eye, "Lookalike-domain and phishing-page checks"],
            ].map(([Icon, t]) => {
              const I = Icon as typeof Eye;
              return (
                <li key={t as string} className="flex items-center gap-3 rounded-lg border border-border bg-panel-2 px-3 py-2">
                  <I className="h-4 w-4 text-accent" aria-hidden /> {t as string}
                </li>
              );
            })}
          </ul>
        </div>
        <p className="text-xs text-muted">Results are estimates, not proof. DeepShield never labels content as fake on AI origin alone.</p>
      </div>

      <div className="flex flex-col p-6">
        <div className="flex items-center justify-between lg:justify-end">
          <div className="lg:hidden">
            <Logo />
          </div>
          <ThemeToggle />
        </div>
        <div className="m-auto w-full max-w-sm">
          <h2 className="text-2xl font-semibold">{mode === "login" ? "Sign in" : "Create your account"}</h2>
          <p className="mt-1 text-sm text-muted">
            {mode === "login" ? "Welcome back." : "The first account created becomes the administrator."}
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label="Email">
              <input className={inputCls} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}>
              <input
                className={inputCls}
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={mode === "register" ? 10 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {mode === "register" && (
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={terms} onChange={(e) => setTerms(e.target.checked)} required />
                <span>
                  I will use DeepShield responsibly and only analyze content I&apos;m entitled to. See the{" "}
                  <Link href="/responsible-use" className="text-accent underline">
                    privacy &amp; responsible-use policy
                  </Link>
                  .
                </span>
              </label>
            )}
            <ErrorNote message={error} />
            <Button type="submit" className="w-full" loading={busy}>
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-muted">
            {mode === "login" ? (
              <>
                New to DeepShield?{" "}
                <Link className="text-accent underline" href="/register">
                  Create an account
                </Link>
              </>
            ) : (
              <>
                Already registered?{" "}
                <Link className="text-accent underline" href="/login">
                  Sign in
                </Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
