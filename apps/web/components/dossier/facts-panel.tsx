"use client";

import type { Item, Verdict } from "@checky/shared";
import { VERDICTS } from "@checky/shared";
import { useState } from "react";
import { toast } from "sonner";
import { VERDICT_META, VerdictChip } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconArrowSquareOut, IconCalculator, IconCalendarDots, IconCircleNotch, IconFileText, IconNewspaper, IconScan, IconSealCheck, IconTextT } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { type DiffPart, fmtDay, type Research, type Review } from "./types";

const d = t.dossier.facts;

/** One established fact: an ink icon, its name, then what was found. Solid: no model wrote it. */
function Fact({ icon: Icon, title, children }: { icon: typeof IconScan; title: string; children: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 border-t border-border py-4 first:border-t-0">
      <Icon className="mt-0.5 size-5 text-foreground" aria-hidden />
      <div className="min-w-0">
        <h4 className="font-bold">{title}</h4>
        <div className="mt-1.5 space-y-2 text-pretty">{children}</div>
      </div>
    </li>
  );
}

function Out({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline decoration-border underline-offset-4 hover:decoration-foreground">
      {children}
      <IconArrowSquareOut className="size-3.5 shrink-0" aria-hidden />
    </a>
  );
}

/** The registry's comparison: words of the original struck when the circulating text drops or changes them. */
function RegistryDiff({ diff }: { diff: DiffPart[] }) {
  if (!diff.some((p) => p.op !== "equal")) return null;
  return (
    <p className="rounded-sm border border-border bg-background p-3 leading-relaxed">
      {diff.map((p, i) =>
        p.op === "equal" ? (
          <span key={i}>{p.a || p.b} </span>
        ) : (
          <span key={i}>
            {p.a && p.op !== "insert" && <del className="text-verdict-false-ink decoration-2">{p.a}</del>}
            {p.a && p.b && p.op === "replace" && " "}
            {p.b && p.op !== "delete" && <ins className="signal-mark no-underline">{p.b}</ins>}{" "}
          </span>
        ),
      )}
    </p>
  );
}

/** « Reprendre ce verdict »: read their rating in code, show it, sign only once the journalist confirms. */
function AdoptReview({ ws, item, review, onSigned }: { ws: string; item: Item; review: Review; onSigned: (item: Item) => void }) {
  const [mapped, setMapped] = useState<{ verdict: Verdict | null } | null>(null);
  const [choice, setChoice] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState(false);

  async function read() {
    setBusy(true);
    try {
      const out = await api<{ verdict: Verdict | null }>(`/workspaces/${ws}/ratings?rating=${encodeURIComponent(review.rating ?? "")}`);
      setMapped(out);
      setChoice(out.verdict);
    } catch {
      toast.error(d.adoptFailed);
    } finally {
      setBusy(false);
    }
  }

  async function adopt() {
    if (!choice) return;
    setBusy(true);
    try {
      const saved = await api<Item>(`/workspaces/${ws}/items/${item.id}/adopt`, {
        method: "POST",
        body: JSON.stringify({
          review: { publisher: review.publisher, url: review.url, rating: review.rating, date: review.date, title: review.title ?? "" },
          verdict: choice,
          publish: false,
        }),
      });
      onSigned(saved);
      setMapped(null);
      toast.success(d.adoptDone);
    } catch {
      toast.error(d.adoptFailed);
    } finally {
      setBusy(false);
    }
  }

  if (!mapped) {
    return (
      <Button variant="outline" size="sm" onClick={read} disabled={busy}>
        {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
        {d.adopt}
      </Button>
    );
  }
  return (
    <div role="group" aria-label={d.adopt} className="rounded-sm border border-border bg-background p-3">
      <p className="text-sm">{mapped.verdict ? d.adoptRead(VERDICT_META[mapped.verdict].label) : d.adoptUnclear}</p>
      <div role="radiogroup" aria-label={t.dossier.sign.verdict} className="mt-2 flex flex-wrap gap-1.5">
        {VERDICTS.map((v) => {
          const m = VERDICT_META[v];
          const Icon = m.icon;
          return (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={choice === v}
              onClick={() => setChoice(v)}
              className={cn(
                "inline-flex h-9 items-center gap-1.5 rounded-sm border px-2.5 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                m.ink,
                choice === v ? cn(m.soft, "border-2 border-current font-bold") : "border-border bg-card hover:bg-muted",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {m.label}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={adopt} disabled={busy || !choice}>
          {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
          {d.adoptConfirm}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setMapped(null)} disabled={busy}>
          {d.adoptCancel}
        </Button>
      </div>
    </div>
  );
}

/** « Ce que l'on sait »: what code established from the sources, without a model. */
export function FactsPanel({
  ws,
  item,
  research,
  canSign,
  onSigned,
}: {
  ws: string;
  item: Item;
  research: Research;
  canSign: boolean;
  onSigned: (item: Item) => void;
}) {
  const { provenance, registry, figures, reviews, published, tone, credibility } = research;
  const signed = typeof item.data.verdict === "string";

  return (
    <section aria-labelledby="facts" className="rounded-md border border-border bg-card px-4 md:px-5">
      <header className="border-b border-border py-4">
        <h3 id="facts" className="font-display text-lg font-bold">
          {d.title}
        </h3>
        <p className="mt-0.5 text-sm text-muted-foreground">{d.lead}</p>
      </header>
      <ul>
        {provenance && (
          <Fact icon={IconScan} title={d.provenance}>
            {provenance.firstSeen && <p className="font-medium">{d.firstSeen(fmtDay(provenance.firstSeen) ?? provenance.firstSeen)}</p>}
            {provenance.firstPage && (
              <p className="text-sm">
                {d.firstPage(fmtDay(provenance.firstPage.date) ?? provenance.firstPage.date, provenance.firstPage.host)}{" "}
                <Out href={provenance.firstPage.url}>{d.open}</Out>
                {provenance.firstPage.pages.length > 1 && (
                  <span className="block text-muted-foreground">
                    {provenance.firstPage.pages.map((q) => `${fmtDay(q.date) ?? q.date} (${q.host})`).join(" · ")}
                  </span>
                )}
                <span className="block text-muted-foreground">
                  {provenance.firstPage.corroborated ? d.pageCorroborated : d.pageAlone}
                </span>
              </p>
            )}
            {provenance.signals.length > 0 && (
              <ul className="list-disc space-y-0.5 pl-5 text-sm">
                {provenance.signals.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            )}
            {provenance.reverse.length > 0 && (
              <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                <span className="text-muted-foreground">{d.reverse}</span>
                {provenance.reverse.map((l) => (
                  <Out key={l.url} href={l.url}>
                    {l.name}
                  </Out>
                ))}
              </p>
            )}
          </Fact>
        )}

        {registry && (
          <Fact icon={IconSealCheck} title={d.registry}>
            <p className="font-medium">
              {d.registryStatus[registry.status] ?? registry.status}
              {(registry.issuer || registry.number) && (
                <span className="font-normal text-muted-foreground"> · {[registry.issuer, registry.number].filter(Boolean).join(" · ")}</span>
              )}
            </p>
            {registry.summary && <p className="text-sm">{registry.summary}</p>}
            <RegistryDiff diff={registry.diff} />
            {registry.status === "not_found" && <p className="text-sm text-muted-foreground">{d.notFoundNote}</p>}
            {registry.url && <Out href={registry.url}>{d.open}</Out>}
          </Fact>
        )}

        {figures.length > 0 && (
          <Fact icon={IconCalculator} title={d.figures}>
            <ul className="space-y-2">
              {figures.map((f, i) => (
                <li key={i} className="grid gap-x-4 gap-y-0.5 text-sm sm:grid-cols-[auto_minmax(0,1fr)]">
                  <span className="text-muted-foreground">{d.claimed}</span>
                  <span className="font-display font-bold tabular">{f.claimed}</span>
                  <span className="text-muted-foreground">{d.official}</span>
                  <span>
                    {f.official ? (
                      <>
                        <span className="font-display font-bold tabular">{f.official.value}</span>
                        {f.official.label && <span> · {f.official.label}</span>}
                        {f.official.asOf && <span className="text-muted-foreground"> · {d.asOf(fmtDay(f.official.asOf) ?? f.official.asOf)}</span>}
                        {f.official.old && <span className="ml-1.5 rounded-sm border border-border px-1 text-xs">{d.old}</span>}
                        {f.official.source && (
                          <span className="block text-muted-foreground">
                            {f.official.url ? <Out href={f.official.url}>{f.official.source}</Out> : f.official.source}
                          </span>
                        )}
                      </>
                    ) : (
                      d.noFigure
                    )}
                  </span>
                  <span className="font-medium sm:col-span-2">{d.figureVerdict[f.verdict] ?? f.verdict}</span>
                </li>
              ))}
            </ul>
          </Fact>
        )}

        {reviews.length > 0 && (
          <Fact icon={IconNewspaper} title={d.factChecks}>
            <ul className="space-y-3">
              {reviews.map((r) => (
                <li key={r.url} className="space-y-1.5">
                  <p className="text-sm">
                    <Out href={r.url}>{d.reviewedBy(r.publisher, fmtDay(r.date))}</Out>
                  </p>
                  {r.title && <p className="text-sm text-muted-foreground">{r.title}</p>}
                  {r.rating && <p className="font-medium">{t.common.quote(r.rating)}</p>}
                  {r.rating && canSign && !signed && <AdoptReview ws={ws} item={item} review={r} onSigned={onSigned} />}
                </li>
              ))}
            </ul>
          </Fact>
        )}

        {published.length > 0 && (
          <Fact icon={IconFileText} title={d.archives}>
            <ul className="space-y-2">
              {published.map((p) => (
                <li key={`${p.newsroom}-${p.title}`} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-sm font-medium">{d.alreadyBy(p.newsroom)}</span>
                  {p.verdict && <VerdictChip verdict={p.verdict} />}
                  <span className="w-full text-sm text-muted-foreground">
                    {p.id ? (
                      <a href={`/verdicts/${p.id}`} target="_blank" rel="noreferrer" className="underline decoration-border underline-offset-4 hover:decoration-foreground">
                        {p.title}
                      </a>
                    ) : (
                      p.title
                    )}
                    {p.at && ` · ${fmtDay(p.at)}`}
                  </span>
                </li>
              ))}
            </ul>
          </Fact>
        )}

        {tone && (
          <Fact icon={IconTextT} title={d.tone}>
            <p className="font-medium">{d.toneLevel[tone.level] ?? tone.level}</p>
            {tone.signals.length > 0 && (
              <ul className="flex flex-wrap gap-1.5 text-sm">
                {tone.signals.map((s, i) => (
                  <li key={i} className="rounded-sm border border-border px-2 py-0.5">
                    <span className="text-muted-foreground">{d.toneKinds[s.kind] ?? s.kind} · </span>{t.common.quote(s.quote)}
                  </li>
                ))}
              </ul>
            )}
          </Fact>
        )}

        {credibility && (
          <Fact icon={IconCalendarDots} title={d.credibility}>
            {(credibility.name || credibility.domain) && <p className="font-medium">{credibility.name ?? credibility.domain}</p>}
            <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-sm">
              {credibility.signals.map((s) => (
                <div key={s.key} className="contents">
                  <dt>
                    {d.credKeys[s.key] ?? s.key}
                    {s.detail && <span className="text-muted-foreground"> · {s.detail}</span>}
                  </dt>
                  <dd className={cn("text-right", s.status === "found" ? "font-bold" : "text-muted-foreground")}>{d.signal[s.status] ?? s.status}</dd>
                </div>
              ))}
            </dl>
            <p className="text-sm text-muted-foreground">{d.credibilityNote}</p>
          </Fact>
        )}
      </ul>
    </section>
  );
}
