"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import PublicCard from "@/components/PublicCard";
import { Button, ErrorNote, Spinner } from "@/components/ui";
import { api, auth } from "@/lib/api";

function Invite() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [inv, setInv] = useState<{ org_name: string; email: string; role: string; inviter: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(!!auth.get());
  }, []);

  useEffect(() => {
    api<typeof inv>(`/invites/${encodeURIComponent(token)}`)
      .then(setInv)
      .catch((e) => setError(e.message));
  }, [token]);

  const accept = async () => {
    setBusy(true);
    try {
      await api("/invites/accept", { method: "POST", json: { token } });
      router.replace("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not accept");
      setBusy(false);
    }
  };

  const q = `invite=${encodeURIComponent(token)}`;
  return (
    <PublicCard title="Workspace invitation">
      {!inv && !error && <Spinner />}
      <ErrorNote message={error} />
      {inv && (
        <>
          <p>
            {inv.inviter ?? "Someone"} invited <strong>{inv.email}</strong> to join <strong>{inv.org_name}</strong> as{" "}
            {inv.role}.
          </p>
          {signedIn ? (
            <Button onClick={accept} loading={busy} className="w-full">
              Accept invitation
            </Button>
          ) : (
            <div className="grid gap-2">
              <Link href={`/register?${q}`} className="rounded-lg bg-accent px-4 py-2 text-center font-medium text-accent-contrast">
                Create an account
              </Link>
              <Link href={`/login?${q}`} className="rounded-lg border border-border px-4 py-2 text-center">
                I already have an account
              </Link>
            </div>
          )}
        </>
      )}
    </PublicCard>
  );
}

export default function InvitePage() {
  return (
    <Suspense>
      <Invite />
    </Suspense>
  );
}
