"use client";

import type { Workspace } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { mutate } from "swr";
import { LoaderCircle } from "lucide-react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";

export default function InvitationPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    // Accept once, even when React runs effects twice in development.
    if (started.current) return;
    started.current = true;
    api<Workspace>(`/invitations/${encodeURIComponent(token)}/accept`, { method: "POST" })
      .then(async (ws) => {
        await mutate("/me");
        router.replace(`/w/${ws.id}/affirmations`);
      })
      .catch(() => setFailed(true));
  }, [token, router]);

  return (
    <div className="mx-auto max-w-lg px-5 py-16">
      <h1 className="page-title">{t.invitation.title}</h1>
      {failed ? (
        <>
          <p className="mt-3 text-muted-foreground">{t.invitation.invalid}</p>
          <Link href="/" className="mt-6 inline-block font-medium underline decoration-border underline-offset-4 hover:decoration-foreground">
            {t.invitation.back}
          </Link>
        </>
      ) : (
        <p className="mt-3 flex items-center gap-2 text-muted-foreground" role="status">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          {t.invitation.joining}
        </p>
      )}
    </div>
  );
}
