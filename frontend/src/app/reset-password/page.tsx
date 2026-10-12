"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import PublicCard from "@/components/PublicCard";
import { Button, ErrorNote, Field, inputCls } from "@/components/ui";
import { api } from "@/lib/api";

function Reset() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError("The passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/auth/reset-password", { method: "POST", json: { token, password } });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <PublicCard title="Choose a new password">
      {done ? (
        <>
          <p role="status">Your password has been changed and all other sessions were signed out.</p>
          <Link href="/login" className="inline-block rounded-lg bg-accent px-4 py-2 font-medium text-accent-contrast">
            Sign in
          </Link>
        </>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="New password" hint="At least 10 characters.">
            <input className={inputCls} type="password" autoComplete="new-password" minLength={10} required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Confirm new password">
            <input className={inputCls} type="password" autoComplete="new-password" minLength={10} required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <ErrorNote message={error} />
          <Button type="submit" className="w-full" loading={busy} disabled={!token}>
            Set new password
          </Button>
          {!token && <p className="text-danger">This link is missing its token. Request a new reset email.</p>}
        </form>
      )}
    </PublicCard>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <Reset />
    </Suspense>
  );
}
