"use client";

import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { IconCaretRight, IconCircleNotch, IconStamp } from "@/lib/icons";
import { claimSteps, StepLine } from "@/components/flow/step-line";
import { Avatar, type ClaimView, StatusLabel, VerdictBadge } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { exact, relative } from "@/lib/when";


function seen(c: ClaimView, now: Date) {
  if (!c.firstSeen) return { at: t.claims.noFirstSeen, ago: null, exactly: undefined };
  const iso = c.firstSeen.toISOString();
  return { at: relative(iso, now), ago: relative(iso, now), exactly: exact(iso) };
}

const b = t.dossier.batch;

/** The public explanation a batch signature would use: the one written, else the reading's. */
function batchReason(c: ClaimView): string {
  const d = c.item.data as { reason?: unknown; analysis?: { reason?: unknown } };
  for (const r of [d.reason, d.analysis?.reason]) if (typeof r === "string" && r.trim().length >= 10) return r.trim();
  return "";
}

/**
 * « Signer les N »: the dossiers whose reading suggests a verdict and that this person may sign.
 * Nothing is signed before the list is shown, each with the verdict and the explanation it will carry.
 */
function BatchSign({ ws, claims }: { ws: string; claims: ClaimView[] }) {
  const { me } = useWorkspace(ws);
  const { mutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const waiting = claims.filter((c) => c.suggested && !c.verdict && me);
  const ready = waiting.filter((c) => batchReason(c));
  if (!waiting.length) return null;

  async function sign() {
    setBusy(true);
    try {
      const out = await api<{ signed: unknown[]; skipped: unknown[] }>(`/workspaces/${ws}/items/sign`, {
        method: "POST",
        body: JSON.stringify({ ids: ready.map((c) => c.item.id), publish: true }),
      });
      if (out.signed.length) toast.success(b.done(out.signed.length));
      if (out.skipped.length) toast(b.skipped(out.skipped.length));
      setOpen(false);
      mutate((key) => typeof key === "string" && key.startsWith(`/workspaces/${ws}/items`));
    } catch {
      toast.error(b.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="batch-sign" className="mx-4 mb-4 rounded-md border border-border bg-card p-4 lg:mx-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 id="batch-sign" className="font-bold">
            {b.bar(waiting.length)}
          </h2>
          <p className="text-sm text-muted-foreground">{ready.length ? b.lead : b.noneReady}</p>
        </div>
        {!open && ready.length > 0 && (
          <Button onClick={() => setOpen(true)}>
            <IconStamp aria-hidden />
            {b.review(ready.length)}
          </Button>
        )}
      </div>
      {open && (
        <div className="mt-4 space-y-4">
          <ul className="divide-y divide-border border-y border-border">
            {waiting.map((c) => {
              const reason = batchReason(c);
              return (
                <li key={c.item.id} className="grid gap-x-4 gap-y-1 py-3 sm:grid-cols-[5.5rem_minmax(0,1fr)_auto]">
                  <span className="font-medium tabular">{c.ref}</span>
                  <div className="min-w-0">
                    <p className="font-medium text-pretty">{c.item.title}</p>
                    <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{reason || b.noReason}</p>
                  </div>
                  <VerdictBadge claim={c} />
                </li>
              );
            })}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button onClick={sign} disabled={busy || !ready.length}>
              {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconStamp aria-hidden />}
              {busy ? b.signing : b.confirm(ready.length)}
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              {b.cancel}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

/** One dossier per line: when it was first seen, what it says, where it stands on the line, the verdict. */
export function DossierList({ ws, claims, now, names }: { ws: string; claims: ClaimView[]; now: Date; names: Map<string, string> }) {
  return (
    <>
      <BatchSign ws={ws} claims={claims} />
      <ul className="border-t border-foreground">
        {claims.map((c, i) => {
          const when = seen(c, now);
          const who = c.assigneeId ? names.get(c.assigneeId) : null;
          const origin = c.origin ? (t.origins[c.origin as keyof typeof t.origins] ?? c.origin) : null;
          return (
            <li key={c.item.id} className="arrive relative border-b border-border" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
              <div className="grid gap-x-6 gap-y-3 px-4 py-4 transition-colors hover:bg-card md:grid-cols-[6.5rem_minmax(0,1fr)_auto] md:items-center lg:px-3 @4xl:grid-cols-[6.5rem_minmax(0,1fr)_13rem_11rem_1.5rem]">
                <p className="flex items-baseline gap-3 md:block">
                  <span className="block font-medium tabular">{c.ref}</span>
                  <time dateTime={c.firstSeen?.toISOString()} className="block text-sm text-muted-foreground tabular" title={when.exactly}>
                    {when.ago ?? when.at}
                  </time>
                </p>
                <div className="min-w-0">
                  <Link
                    href={`/w/${ws}/claims/${c.item.id}`}
                    className="block font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset"
                  >
                    {c.item.title}
                  </Link>
                  <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                    <StatusLabel status={c.status} />
                    {origin && <span>{origin}</span>}
                    <span className="tabular">{t.claims.sources(c.sources)}</span>
                  </p>
                </div>
                <StepLine variant="mini" states={claimSteps(c)} className="hidden @4xl:flex" />
                <div className="flex items-center gap-3 md:justify-end @4xl:justify-start">
                  <VerdictBadge claim={c} />
                  {who && <Avatar name={who} className="@4xl:hidden" />}
                </div>
                <span className="hidden items-center justify-end @4xl:flex">
                  {who ? <Avatar name={who} /> : <IconCaretRight className="size-4 text-muted-foreground" aria-hidden />}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}
