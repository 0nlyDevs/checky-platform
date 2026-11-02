"use client";

import type { Item, Verdict } from "@fanilo/shared";
import { VERDICTS } from "@fanilo/shared";
import { AlertDialog } from "radix-ui";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { PublicStrip } from "@/components/claims/publication-panel";
import { VERDICT_META } from "@/components/claims/verdict";
import { type Byline, fmtWhen } from "@/components/dossier/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconCircleNotch, IconSparkle, IconStamp, IconWarning } from "@/lib/icons";
import { cn } from "@/lib/utils";

const s = t.dossier.sign;

/**
 * A verdict as the dossier states it: icon and word in Bricolage Grotesque, on its soft ground. Dashed while it
 * is only a suggestion; solid, with the newsroom's and the journalist's names, once signed.
 */
export function VerdictBlock({
  verdict,
  suggested,
  byline,
  children,
}: {
  verdict: Verdict;
  suggested: boolean;
  byline?: Byline | null;
  children?: React.ReactNode;
}) {
  const m = VERDICT_META[verdict];
  const Icon = m.icon;
  return (
    <div className={cn("verdict-land rounded-md border-2 border-current p-4 md:p-5", suggested ? "border-dashed bg-card" : m.soft, m.ink)}>
      <p className="flex items-center gap-2.5 font-display text-3xl font-extrabold tracking-tight md:text-4xl">
        <Icon className="size-8 shrink-0" aria-hidden />
        {m.label}
      </p>
      <p className="mt-1.5 flex items-center gap-1.5 text-sm font-bold">
        {suggested ? <IconSparkle className="size-3.5" aria-hidden /> : <IconStamp className="size-3.5" aria-hidden />}
        {suggested ? t.verify.suggestedBy : byline ? s.signedBy(byline.journalist, byline.newsroom, fmtWhen(byline.signedAt) ?? "") : t.site.pub.file.confirmed}
      </p>
      {children}
    </div>
  );
}

function errorText(e: unknown) {
  return e instanceof ApiError ? (s.errors[e.code] ?? s.failed) : s.failed;
}

/**
 * 03 La conclusion. Knowing is not publishing: the reading only suggests, the journalist picks the
 * verdict, writes the public explanation and signs. « Signer et publier » is the screen's one
 * citron action: the journalist who signs publishes.
 */
export function VerdictDecision({
  ws,
  item,
  suggested,
  reasonDraft,
  byline,
  canSign,
  isPublic,
  onSaved,
}: {
  ws: string;
  item: Item;
  suggested: Verdict | null;
  reasonDraft: string;
  byline: Byline | null;
  canSign: boolean;
  isPublic: boolean;
  onSaved: (item: Item) => void;
}) {
  const signedVerdict = typeof item.data.verdict === "string" && item.data.verdict in VERDICT_META ? (item.data.verdict as Verdict) : null;
  const signed = Boolean(signedVerdict && item.data.signed_by);
  const published = item.status === "published";
  const [editing, setEditing] = useState(!signed);
  const [choice, setChoice] = useState<Verdict | null>(signedVerdict ?? suggested);
  const [picking, setPicking] = useState(!suggested && !signedVerdict);
  const [reason, setReason] = useState(typeof item.data.reason === "string" && item.data.reason ? item.data.reason : reasonDraft);
  const [busy, setBusy] = useState(false);
  // A journalist always confirms: signing opens a dialog that says what will be signed and published.
  const [asking, setAsking] = useState<{ publish: boolean; verdict: Verdict; text: string } | null>(null);
  const [focusIndex, setFocusIndex] = useState(() => Math.max(0, VERDICTS.indexOf(choice ?? "true")));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const base = `/workspaces/${ws}/items/${item.id}`;

  function move(e: React.KeyboardEvent, i: number) {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (i + step + VERDICTS.length) % VERDICTS.length;
    setFocusIndex(next);
    refs.current[next]?.focus();
  }

  async function sign(publish: boolean, verdict: Verdict | null = choice, text: string = reason) {
    if (!verdict) return;
    setBusy(true);
    try {
      const saved = await api<Item>(`${base}/sign`, { method: "POST", body: JSON.stringify({ verdict, reason: text.trim(), publish }) });
      onSaved(saved);
      setEditing(false);
      const word = VERDICT_META[verdict].label;
      toast.success(saved.status === "published" ? s.published(word) : s.done(word));
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const confirmDialog = (
    <AlertDialog.Root open={!!asking} onOpenChange={(open) => !open && setAsking(null)}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <AlertDialog.Content className="fixed top-[18vh] left-1/2 z-50 w-[min(480px,calc(100vw-2rem))] -translate-x-1/2 rounded-[22px] border border-border bg-popover p-5 text-popover-foreground shadow-2xl outline-none max-sm:top-4 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0">
          {asking && (
            <>
              <AlertDialog.Title className="font-display text-lg font-bold text-balance">{t.detail.decision.title(VERDICT_META[asking.verdict].label)}</AlertDialog.Title>
              <AlertDialog.Description asChild>
                <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
                  <li>{t.detail.decision.visible}</li>
                  {asking.publish && (
                    <li>
                      <span className="font-bold text-foreground">{s.strip.after} :</span> {s.strip.afterText}
                    </li>
                  )}
                </ul>
              </AlertDialog.Description>
              {suggested && suggested !== asking.verdict && (
                <p className="mt-3 flex items-start gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
                  <IconWarning className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {s.againstAi(VERDICT_META[suggested].label)}
                </p>
              )}
              <div className="mt-5 flex flex-wrap justify-end gap-2">
                <AlertDialog.Cancel asChild>
                  <Button variant="ghost" size="xl">
                    {s.cancel}
                  </Button>
                </AlertDialog.Cancel>
                <AlertDialog.Action asChild>
                  <Button variant="action" size="xl" onClick={() => void sign(asking.publish, asking.verdict, asking.text)}>
                    <IconStamp aria-hidden />
                    {s.signPublish}
                  </Button>
                </AlertDialog.Action>
              </div>
            </>
          )}
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );

  // Signed: the solid block, the byline, and publication when it is still to come.
  if (signed && signedVerdict && !editing) {
    const signedReason = typeof item.data.reason === "string" ? item.data.reason : "";
    return (
      <div className="space-y-4">
        <VerdictBlock verdict={signedVerdict} suggested={false} byline={byline}>
          {signedReason && <p className="mt-3 max-w-[70ch] text-pretty text-foreground">{signedReason}</p>}
        </VerdictBlock>
        {published && <p className="text-sm text-muted-foreground">{isPublic ? s.publishedNote : s.privateNote}</p>}
        {!published && canSign && (
          <Button variant="action" size="xl" onClick={() => setAsking({ publish: true, verdict: signedVerdict, text: signedReason })} disabled={busy || signedReason.trim().length < 10}>
            {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconStamp aria-hidden />}
            {s.signPublish}
          </Button>
        )}
        {confirmDialog}
        {canSign && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="block text-sm text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
          >
            {s.change}
          </button>
        )}
      </div>
    );
  }

  const tooShort = reason.trim().length < 10;
  const against = suggested && choice && choice !== suggested ? suggested : null;

  return (
    <div className="space-y-5">
      <p className="max-w-[70ch] text-pretty text-muted-foreground">{s.lead}</p>

      {choice && !picking ? (
        <VerdictBlock verdict={choice} suggested={choice === suggested && !signedVerdict}>
          {canSign && (
            <button
              type="button"
              onClick={() => setPicking(true)}
              className="mt-3 text-sm font-medium text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground"
            >
              {s.other}
            </button>
          )}
        </VerdictBlock>
      ) : (
        <div role="radiogroup" aria-label={s.verdict} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {VERDICTS.map((v, i) => {
            const m = VERDICT_META[v];
            const Icon = m.icon;
            const on = choice === v;
            return (
              <button
                key={v}
                ref={(el) => {
                  refs.current[i] = el;
                }}
                type="button"
                role="radio"
                aria-checked={on}
                tabIndex={i === focusIndex ? 0 : -1}
                disabled={!canSign}
                onKeyDown={(e) => move(e, i)}
                onFocus={() => setFocusIndex(i)}
                onClick={() => {
                  setChoice(v);
                  setPicking(false);
                }}
                className={cn(
                  "flex h-12 items-center justify-center gap-2 rounded-md border text-sm font-medium transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:text-muted-foreground",
                  m.ink,
                  on ? cn(m.soft, "border-2 border-current font-bold") : "border-border bg-card hover:bg-muted",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {m.label}
              </button>
            );
          })}
        </div>
      )}

      {against && (
        <p className="flex items-start gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
          <IconWarning className="mt-0.5 size-4 shrink-0" aria-hidden />
          {s.againstAi(VERDICT_META[against].label)}
        </p>
      )}

      {canSign ? (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="public-reason" className="font-bold">
              {s.reason}
            </Label>
            <p id="public-reason-hint" className="text-sm text-muted-foreground">
              {s.reasonHint}
            </p>
            <textarea
              id="public-reason"
              aria-describedby="public-reason-hint"
              rows={4}
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full resize-y rounded-md border border-input bg-card px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
            />
          </div>

          <PublicStrip />

          <div className="flex flex-wrap items-center gap-3">
            <Button variant="action" size="xl" disabled={busy || !choice || tooShort} onClick={() => choice && setAsking({ publish: true, verdict: choice, text: reason })}>
              {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconStamp aria-hidden />}
              {busy ? s.signing : s.signPublish}
            </Button>
            {signed && (
              <Button variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
                {s.cancel}
              </Button>
            )}
            {tooShort && choice && <span className="text-sm text-muted-foreground">{s.reasonShort}</span>}
          </div>
        </>
      ) : null}
      {confirmDialog}
    </div>
  );
}
