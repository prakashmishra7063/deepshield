"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import PublicCard from "@/components/PublicCard";
import { Button, ErrorNote, Field, inputCls } from "@/components/ui";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/forgot-password", { method: "POST", json: { email } });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <PublicCard title="Reset your password">
      {sent ? (
        <p role="status">
          If an account exists for <strong>{email}</strong>, we&apos;ve sent a link to reset the password. It expires in
          an hour.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-muted">Enter your account email and we&apos;ll send you a reset link.</p>
          <Field label="Email">
            <input className={inputCls} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <ErrorNote message={error} />
          <Button type="submit" className="w-full" loading={busy}>
            Send reset link
          </Button>
        </form>
      )}
      <Link href="/login" className="block text-accent underline">
        Back to sign in
      </Link>
    </PublicCard>
  );
}
