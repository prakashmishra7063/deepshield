"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import PublicCard from "@/components/PublicCard";
import { ErrorNote, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"working" | "done" | "error">("working");
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (!token) {
      setState("error");
      setError("This verification link is missing its token.");
      return;
    }
    api("/auth/verify-email", { method: "POST", json: { token } })
      .then(() => setState("done"))
      .catch((e) => {
        setState("error");
        setError(e.message);
      });
  }, [token]);

  return (
    <PublicCard title="Email verification">
      {state === "working" && <Spinner label="Verifying" />}
      {state === "done" && (
        <>
          <p>Your email address is verified. You can start scanning content now.</p>
          <Link href="/dashboard" className="inline-block rounded-lg bg-accent px-4 py-2 font-medium text-accent-contrast">
            Go to dashboard
          </Link>
        </>
      )}
      {state === "error" && (
        <>
          <ErrorNote message={error} />
          <p className="text-muted">Sign in and use “Resend email” in the banner to get a new link.</p>
          <Link href="/login" className="text-accent underline">
            Sign in
          </Link>
        </>
      )}
    </PublicCard>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <Verify />
    </Suspense>
  );
}
