"use client";

import type { Me } from "@fanilo/shared";
import Link from "next/link";
import useSWR from "swr";
import { RequestForm, useVerification } from "@/components/verification/request-form";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconHourglass, IconLockSimple, IconSealCheck, IconWarning } from "@/lib/icons";
import { relative } from "@/lib/when";
import { cn } from "@/lib/utils";

const v = t.verification;

/** « Rédaction vérifiée par Checky »: on public cards and pages, never colour alone. */
export function VerifiedBadge({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-bold", className)}>
      <IconSealCheck className="size-4 shrink-0" aria-hidden />
      {v.badge}
    </span>
  );
}

/**
 * Under the desk bar while the newsroom is not verified: it works privately and nothing leaves.
 * Quiet (ink on card), one link to the request in Réglages.
 */
export function VerificationBanner({ ws }: { ws: string }) {
  const { data: me } = useSWR<Me>("/me", fetcher);
  const status = me?.memberships.find((m) => m.workspace_id === ws)?.verification;
  if (!status || status === "approved") return null;
  const Icon = status === "pending" ? IconHourglass : status === "refused" ? IconWarning : IconLockSimple;
  const text = status === "pending" ? v.banner.pending : status === "refused" ? v.banner.refused : v.banner.none;
  const action = status === "pending" ? v.banner.see : status === "refused" ? v.banner.fix : v.banner.ask;
  return (
    <div role="status" className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm lg:px-8">
        <Icon className="size-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">{text}</span>
        <Link href={`/w/${ws}/parametres#verification` as never} className="font-bold underline underline-offset-4">
          {action}
        </Link>
      </div>
    </div>
  );
}

/** Réglages → « Vérification de la rédaction »: the status, the reason of a refusal, the form. */
export function VerificationSection({ ws }: { ws: string }) {
  const { data } = useVerification(ws);
  if (!data) return null;
  const s = data.status;
  return (
    <section id="verification" aria-labelledby="verification-title" className="scroll-mt-24 rounded-lg border border-border bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="verification-title" className="font-display text-lg font-bold">
          {v.section.title}
        </h2>
        {s === "approved" ? (
          <VerifiedBadge />
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-foreground px-2.5 py-0.5 text-sm font-bold">
            {s === "pending" ? <IconHourglass className="size-4" aria-hidden /> : s === "refused" ? <IconWarning className="size-4" aria-hidden /> : <IconLockSimple className="size-4" aria-hidden />}
            {v.status[s]}
          </span>
        )}
      </div>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        {s === "approved"
          ? v.section.approved
          : s === "pending" && data.submitted_at
            ? v.section.pending(relative(data.submitted_at, new Date()))
            : s === "none"
              ? v.section.none
              : v.form.lead}
      </p>
      {s === "refused" && data.reason && (
        <p className="mt-3 rounded-md bg-verdict-false-soft px-3 py-2.5 text-sm text-verdict-false-ink">{v.section.refused(data.reason)}</p>
      )}
      {s !== "approved" && (
        <div className="mt-5">
          {s === "none" && <p className="mb-5 max-w-prose text-sm">{v.form.lead}</p>}
          <RequestForm ws={ws} />
        </div>
      )}
    </section>
  );
}
