"use client";

import type { Status, Verdict } from "@fanilo/shared";
import { VERDICTS } from "@fanilo/shared";
import { useRef, useState } from "react";
import { IconSparkle, IconWarning } from "@/lib/icons";
import { type ClaimView, VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

/** The status a verdict moves the claim to: confirmed → Vérifié, cleared → back to En cours. */
export function statusAfter(verdict: Verdict | null, status: Status): Status {
  if (verdict) return status === "to_check" || status === "in_progress" ? "verified" : status;
  return status === "verified" ? "in_progress" : status;
}

/**
 * The one consequential act on a claim. Choosing a verdict never commits on its own: a recap says
 * what it will change (team, card, status) and warns when it goes against the AI's suggestion.
 * Arrow keys move between the four verdicts (one Tab stop); Enter or a click opens the recap.
 */
export function VerdictDecision({
  claim,
  canEdit,
  sourceCount,
  onDecide,
}: {
  claim: ClaimView;
  canEdit: boolean;
  sourceCount: number;
  onDecide: (verdict: Verdict | null) => Promise<void>;
}) {
  const [pending, setPending] = useState<Verdict | null>(null);
  const [saving, setSaving] = useState(false);
  const [focusIndex, setFocusIndex] = useState(() => Math.max(0, VERDICTS.indexOf((claim.verdict ?? "true") as Verdict)));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const suggestion = claim.suggested && !claim.verdict ? claim.suggested : null;

  function move(e: React.KeyboardEvent, i: number) {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (i + step + VERDICTS.length) % VERDICTS.length;
    setFocusIndex(next);
    refs.current[next]?.focus();
  }

  async function confirm() {
    if (!pending) return;
    setSaving(true);
    await onDecide(pending);
    setSaving(false);
    setPending(null);
  }

  const nextStatus = pending ? statusAfter(pending, claim.status as Status) : null;

  return (
    <div className="space-y-4">
      {/* The conclusion as a block: dashed while it is the AI's suggestion, solid once a journalist confirmed it. */}
      {(claim.verdict ?? suggestion) && (
        <VerdictBlock verdict={(claim.verdict ?? suggestion)!} suggested={!claim.verdict}>
          {suggestion && canEdit && !pending && (
            <Button variant="action" size="lg" className="mt-4 h-11 px-4" onClick={() => setPending(suggestion)}>
              {t.detail.decision.review(VERDICT_META[suggestion].label)}
            </Button>
          )}
        </VerdictBlock>
      )}

      <div role="radiogroup" aria-label={t.detail.verdictTitle} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {VERDICTS.map((v, i) => {
          const m = VERDICT_META[v];
          const Icon = m.icon;
          const active = claim.verdict === v;
          const chosen = pending === v;
          return (
            <button
              key={v}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={i === focusIndex ? 0 : -1}
              disabled={!canEdit}
              onKeyDown={(e) => move(e, i)}
              onFocus={() => setFocusIndex(i)}
              onClick={() => setPending(active ? null : v)}
              className={cn(
                "flex h-11 items-center justify-center gap-2 rounded-md border text-sm font-medium transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60",
                active ? cn(m.soft, m.ink, "border-2 border-current font-bold") : cn("border-border bg-card hover:bg-accent", m.ink),
                chosen && !active && "border-current ring-2 ring-current/25",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {m.label}
            </button>
          );
        })}
      </div>

      {pending && (
        <div role="alertdialog" aria-labelledby="decision-title" className="rounded-lg border border-border bg-card p-4">
          <p id="decision-title" className="font-semibold">
            {t.detail.decision.title(VERDICT_META[pending].label)}
          </p>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            <li>{t.detail.decision.visible}</li>
            {nextStatus && nextStatus !== claim.status && <li>{t.detail.decision.status(t.status[nextStatus])}</li>}
            <li>{t.detail.decision.sources(sourceCount)}</li>
          </ul>
          {claim.suggested && claim.suggested !== pending && (
            <p className="mt-3 flex items-start gap-2 rounded-md bg-verdict-misleading-soft px-3 py-2 text-sm text-verdict-misleading-ink">
              <IconWarning className="mt-0.5 size-4 shrink-0" aria-hidden />
              {t.detail.decision.againstAi(VERDICT_META[claim.suggested].label)}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={confirm} disabled={saving} autoFocus>
              {t.detail.decision.confirm(VERDICT_META[pending].label)}
            </Button>
            <Button variant="ghost" onClick={() => setPending(null)} disabled={saving}>
              {t.detail.cancel}
            </Button>
          </div>
        </div>
      )}

      {canEdit && claim.verdict && !pending && (
        <button
          type="button"
          onClick={() => onDecide(null)}
          className="text-sm text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
        >
          {t.detail.clearVerdict}
        </button>
      )}
      {!canEdit && <p className="text-sm text-muted-foreground">{t.detail.readOnly}</p>}
    </div>
  );
}

/** A verdict as the dossier states it: icon and word in Archivo, on its soft ground. */
function VerdictBlock({ verdict, suggested, children }: { verdict: Verdict; suggested: boolean; children?: React.ReactNode }) {
  const m = VERDICT_META[verdict];
  const Icon = m.icon;
  return (
    <div className={cn("verdict-land rounded-md border-2 border-current p-4 md:p-5", suggested && "border-dashed", m.soft, m.ink)}>
      <p className="flex items-center gap-2.5 font-display text-3xl font-extrabold tracking-tight md:text-4xl">
        <Icon className="size-8 shrink-0" aria-hidden />
        {m.label}
      </p>
      <p className="mt-1.5 flex items-center gap-1.5 text-sm font-bold">
        {suggested && <IconSparkle className="size-3.5" aria-hidden />}
        {suggested ? t.verify.suggestedBy : t.site.pub.file.confirmed}
      </p>
      {children}
    </div>
  );
}
