import Link from "next/link";
import { IconArrowSquareOut, IconBooks, IconCalculator, IconCalendarDots, IconNewspaper, IconSealCheck, IconStamp, type Icon } from "@/lib/icons";
import { VerdictChip } from "@/components/claims/verdict";
import { type CrewResult, type FigureCheck, frDate, hostOf, type Provenance } from "@/components/crew/types";
import { RegistryDiff } from "@/components/registre/registry-diff";
import type { MatchResult } from "@/components/registre/types";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const k = t.crew;
const FACT_AGENTS = ["Provenance", "Registre", "Chiffres", "Fact-checkers", "Archives"];

function Card({ icon: Icon, title, i, wide, children }: { icon: Icon; title: string; i: number; wide?: boolean; children: React.ReactNode }) {
  return (
    <article className={cn("arrive rounded-md border border-border bg-card p-4", wide && "md:col-span-2")} style={{ "--i": i } as React.CSSProperties}>
      <h3 className="flex items-center gap-2 font-display text-sm font-bold">
        <Icon className="size-4 shrink-0" aria-hidden />
        {title}
      </h3>
      <div className="mt-2 space-y-2 text-sm">{children}</div>
    </article>
  );
}

function Out({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold underline underline-offset-4">
      {children}
      <IconArrowSquareOut className="size-3 shrink-0" aria-hidden />
    </a>
  );
}

function ProvenanceFacts({ p, media }: { p: Provenance; media: boolean }) {
  const first = frDate(p.first_seen);
  return (
    <>
      {first && (
        <p>
          <span className="font-bold">{k.provenance.first(first)}</span>
          {p.first_seen_basis && <span className="text-muted-foreground"> · {k.provenance.basis[p.first_seen_basis] ?? p.first_seen_basis}</span>}
          {p.days_old != null && <span className="text-muted-foreground"> · {k.provenance.ago(p.days_old)}</span>}
        </p>
      )}
      {p.verdict_hint === "old_media_new_caption" && <p className="rounded-sm bg-muted px-2.5 py-1.5 font-bold text-pretty">{k.provenance.hint}</p>}
      {p.signals.map((s, i) => (
        <p key={i} className="text-pretty">
          {s.detail}
        </p>
      ))}
      {media && p.no_trace && <p className="text-muted-foreground">{k.provenance.noTrace}</p>}
      {!!p.reverse_links.length && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-muted-foreground">{k.provenance.reverse} :</span>
          {p.reverse_links.map((x) => (
            <Out key={x.name} href={x.url}>
              {x.name}
            </Out>
          ))}
        </p>
      )}
    </>
  );
}

function RegistryFacts({ r }: { r: MatchResult }) {
  const original = r.communique;
  const issued = frDate(original?.issued_on);
  return (
    <>
      {(r.issuer || r.number) && (
        <p className="text-muted-foreground">
          {[r.issuer, r.number && `N° ${r.number}`].filter(Boolean).join(" · ")}
          {issued && ` · ${k.registry.issued(issued)}`}
        </p>
      )}
      <RegistryDiff diff={r.diff ?? []} summary={r.summary} status={r.status} changedNumbers={r.changed_numbers} />
      {!!r.contacts?.length && (
        <p className="text-pretty">
          <span className="font-bold">{k.registry.contacts} :</span> {r.contacts.map((x) => [x.name, x.role, x.institution].filter(Boolean).join(", ")).join(" · ")}
        </p>
      )}
      {original?.url && <Out href={original.url}>{k.registry.open}</Out>}
    </>
  );
}

function FigureFacts({ list }: { list: FigureCheck[] }) {
  return (
    <ul className="divide-y divide-border">
      {list.map((f, i) => {
        const asOf = frDate(f.figure?.as_of);
        return (
          <li key={i} className="py-2 first:pt-0 last:pb-0">
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-muted-foreground">{k.figures.claimed}</span>
              <span className="font-display font-bold tabular">{f.claimed}</span>
              <span className={cn("ml-auto rounded-sm px-1.5 py-px text-xs font-bold", f.verdict === "differs" ? "bg-foreground text-background" : "bg-muted")}>{k.figures.verdict[f.verdict] ?? f.verdict}</span>
            </p>
            {!f.figure && f.summary && <p className="mt-1 text-pretty text-muted-foreground">{f.summary}</p>}
            {f.figure && (
              <p className="mt-1 text-pretty">
                <span className="text-muted-foreground">{k.figures.official} · </span>
                <span className="font-bold">
                  {f.figure.label} : {f.figure.value}
                  {f.figure.unit ? ` ${f.figure.unit}` : ""}
                </span>
                {f.figure.source_name && <span className="text-muted-foreground"> · {f.figure.source_name}</span>}
                {asOf && <span className="text-muted-foreground"> · {k.figures.asOf(asOf)}</span>}
                {f.figure.old && <span className="font-bold"> · {k.figures.old}</span>}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The facts, first: what code found without interpreting it (the file's first trace, the registry
 * original, official figures, fact-checkers' reviews, verdicts other newsrooms signed, our archives).
 * The checks that could not run this time are named, so silence is never read as « nothing found ».
 */
export function Facts({ r, ws }: { r: CrewResult; ws: string }) {
  const cards: React.ReactNode[] = [];
  const media = r.kind === "image" || r.kind === "video";
  if (r.provenance)
    cards.push(
      <Card key="provenance" icon={IconCalendarDots} title={k.provenance.title} i={cards.length}>
        <ProvenanceFacts p={r.provenance} media={media} />
      </Card>,
    );
  if (r.registry && r.registry.status !== "none")
    cards.push(
      <Card key="registry" icon={IconStamp} title={k.registry.title} i={cards.length} wide={!!r.registry.diff?.length}>
        <RegistryFacts r={r.registry} />
      </Card>,
    );
  if (r.figures?.length)
    cards.push(
      <Card key="figures" icon={IconCalculator} title={k.figures.title} i={cards.length}>
        <FigureFacts list={r.figures} />
      </Card>,
    );
  if (r.fact_checks?.length)
    cards.push(
      <Card key="checks" icon={IconSealCheck} title={k.factChecks.title} i={cards.length}>
        <ul className="space-y-3">
          {r.fact_checks.map((x) => (
            <li key={x.url}>
              <p className="font-bold">{k.factChecks.by(x.publisher, frDate(x.date))}</p>
              {x.rating && <p>{k.factChecks.rating(x.rating)}</p>}
              <a href={x.url} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex items-start gap-1 text-pretty underline underline-offset-4">
                {x.title || hostOf(x.url)}
                <IconArrowSquareOut className="mt-1 size-3 shrink-0" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">{k.factChecks.note}</p>
      </Card>,
    );
  if (r.published?.length)
    cards.push(
      <Card key="published" icon={IconNewspaper} title={k.published.title} i={cards.length}>
        <ul className="space-y-3">
          {r.published.map((x) => (
            <li key={x.id}>
              <p className="flex flex-wrap items-center gap-2">
                <VerdictChip verdict={x.verdict} />
                <span className="font-bold">{k.published.by(x.newsroom)}</span>
              </p>
              <p className="mt-1 text-pretty">{x.title}</p>
              <p className="mt-0.5 text-muted-foreground">
                {frDate(x.published_at)} ·{" "}
                <Link href={`/verifies/${x.id}` as never} className="font-bold text-foreground underline underline-offset-4">
                  {k.published.open}
                </Link>
              </p>
            </li>
          ))}
        </ul>
      </Card>,
    );
  if (r.archives?.length)
    cards.push(
      <Card key="archives" icon={IconBooks} title={k.archives.title} i={cards.length}>
        <ul className="space-y-3">
          {r.archives.map((x) => (
            <li key={x.source_id}>
              <p className="font-bold text-pretty">{x.title}</p>
              <p className="text-muted-foreground">
                {frDate(x.published_at) ?? k.undated}
                {x.item_id && (
                  <>
                    {" · "}
                    <Link href={`/w/${ws}/affirmations/${x.item_id}` as never} className="font-bold text-foreground underline underline-offset-4">
                      {k.archives.open}
                    </Link>
                  </>
                )}
              </p>
              <p className="mt-0.5 line-clamp-2 text-pretty text-muted-foreground">{x.text}</p>
            </li>
          ))}
        </ul>
      </Card>,
    );
  const notChecked = (r.trace ?? []).filter((a) => FACT_AGENTS.includes(a.agent) && ["skipped", "failed", "timeout"].includes(a.status));

  return (
    <section>
      <h2 className="font-display text-2xl font-bold">{k.facts.title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{k.facts.lead}</p>
      {cards.length ? <div className="mt-4 grid items-start gap-3 md:grid-cols-2">{cards}</div> : <p className="mt-3 text-muted-foreground">{k.facts.none}</p>}
      {!!notChecked.length && (
        <p className="mt-3 text-sm text-pretty text-muted-foreground">
          <span className="font-bold text-foreground">{k.facts.notChecked} :</span> {notChecked.map((a) => (a.summary ? `${a.agent} (${a.summary})` : a.agent)).join(" · ")}
        </p>
      )}
    </section>
  );
}
