import { IconArrowSquareOut } from "@/lib/icons";
import { VERDICT_META } from "@/components/claims/verdict";
import { type Confidence, type CrewResult, frDate } from "@/components/crew/types";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

const L = t.crew.lecture;
const c = t.linkCheck;

/** « Comment c'est calculé »: each component with its points, from the API as computed. */
function How({ conf }: { conf: Confidence }) {
  return (
    <details className="rounded-md border border-border bg-card p-3">
      <summary className="cursor-pointer text-sm font-bold">{L.how}</summary>
      <p className="mt-2 text-sm text-muted-foreground">{L.howLead}</p>
      <table className="mt-3 w-full text-sm">
        <tbody className="divide-y divide-border">
          {conf.components.map((x) => (
            <tr key={x.key}>
              <th scope="row" className="py-1.5 pr-3 text-left align-top font-bold">
                {L.components[x.key] ?? x.key}
              </th>
              <td className="py-1.5 pr-3 align-top text-pretty text-muted-foreground">{x.detail}</td>
              <td className="py-1.5 text-right align-top font-display font-bold whitespace-nowrap tabular">{L.points(x.points, x.maximum)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted-foreground">{L.meaning}</p>
    </details>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h3 className="text-sm font-bold">{title}</h3>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-pretty">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

/** No reading (AI off, or too little read): the code's strength of the facts, solid, never a verdict. */
function FactsStrength({ r }: { r: CrewResult }) {
  const conf = r.confidence;
  const synthesis = r.trace?.find((x) => x.agent === "Synthèse")?.status;
  const reason = r.ai_enabled === false ? "no_ai" : synthesis === "failed" || synthesis === "timeout" ? "ai_failed" : "no_evidence";
  return (
    <section className="space-y-3">
      <p className="text-muted-foreground">{t.crew.noLecture[reason]}. {t.verify.noConclusion}</p>
      {conf && conf.direction !== "none" && (
        <div className="rounded-md border border-border bg-card p-5">
          <h2 className="font-display text-lg font-bold">{L.factsOnly}</h2>
          <p className="mt-1 font-display text-3xl font-extrabold tabular">{L.score(conf.score, L.level[conf.level])}</p>
          <p className="mt-1 font-bold">{L.direction[conf.direction]}</p>
          <p className="mt-1 text-sm text-muted-foreground">{L.factsOnlyLead}</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <List title={L.reasons} items={conf.reasons} />
            <List title={L.missing} items={conf.missing} />
          </div>
          <div className="mt-4">
            <How conf={conf} />
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * « Lecture de Checky »: what the model read in the numbered facts, dashed because it is a
 * suggestion. The percentage beside the verdict is computed by code from the evidence.
 */
export function Lecture({ r }: { r: CrewResult }) {
  const a = r.analysis;
  if (!a) return <FactsStrength r={r} />;
  const m = VERDICT_META[a.verdict];
  const Icon = m.icon;
  const conf = a.confidence ?? r.confidence;
  const missing = [...(conf?.missing ?? []), ...(a.missing ? [a.missing] : [])];
  const rumour = frDate(a.first_seen);
  const byN = new Map((r.numbered ?? []).map((x) => [x.n, x]));
  const criticDown = r.trace?.some((x) => x.agent === "Contradicteur" && (x.status === "failed" || x.status === "timeout"));

  return (
    <section className="verdict-land">
      <h2 className="font-display text-2xl font-bold">{L.title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{L.by}</p>
      <div className={cn("mt-3 rounded-md border-2 border-dashed border-current p-5 md:p-6", m.soft, m.ink)}>
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <p className="flex items-center gap-3 font-display text-4xl font-extrabold tracking-tight md:text-5xl">
            <Icon className="size-9 shrink-0 md:size-11" aria-hidden />
            {m.label}
          </p>
          {conf && (
            <p className="md:text-right">
              <span className="block font-display text-3xl font-extrabold tabular">{L.score(conf.score, L.level[conf.level])}</span>
              <span className="text-sm font-bold">{L.scoreLabel}</span>
            </p>
          )}
        </div>
        {a.reason && <p className="mt-4 max-w-[70ch] text-lg text-pretty text-foreground">{a.reason}</p>}
        {conf && <p className="mt-2 max-w-[70ch] text-sm text-pretty text-foreground">{L.meaning}</p>}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <List title={L.reasons} items={conf?.reasons ?? []} />
        <List title={L.missing} items={missing} />
      </div>

      {!!a.evidence.length && (
        <div className="mt-5">
          <h3 className="text-sm font-bold">{L.restsOn}</h3>
          <ul className="mt-2 grid gap-2 md:grid-cols-2">
            {a.evidence.map((e, i) => {
              const src = byN.get(e.n ?? e.result);
              const url = e.url || src?.url;
              const when = frDate(e.source_date);
              return (
                <li key={i} className="arrive rounded-md border border-border bg-card p-3 text-sm" style={{ "--i": i } as React.CSSProperties}>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="rounded-sm bg-muted px-1.5 py-px text-xs font-bold">{c.stance[e.stance]}</span>
                    <span className="font-display text-xs font-bold tabular">[{e.n ?? e.result}]</span>
                    {url ? (
                      <a href={url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 font-bold hover:underline">
                        <span className="truncate">{e.source_title || src?.title}</span>
                        <IconArrowSquareOut className="size-3 shrink-0" aria-hidden />
                      </a>
                    ) : (
                      <span className="font-bold">{e.source_title || src?.title}</span>
                    )}
                  </p>
                  <blockquote className="quote mt-1.5 text-pretty text-muted-foreground">« {e.quote} »</blockquote>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {when ?? t.crew.undated}
                    {e.days_before != null && ` · ${L.before(e.days_before)}`}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="mt-5 space-y-1 text-sm">
        <h3 className="font-bold">{L.dates}</h3>
        {rumour && <p>{L.rumour(rumour)}</p>}
        {a.date_check === "downgraded" && <p className="font-bold text-pretty">{L.downgraded}</p>}
        {a.date_check === "old_evidence" && <p className="font-bold text-pretty">{L.oldEvidence}</p>}
      </div>

      {!!r.critique?.length && (
        <div className="mt-5 rounded-md border border-dashed border-foreground/40 p-4">
          <h3 className="text-sm font-bold">{L.critique}</h3>
          <ul className="mt-2 space-y-3 text-sm">
            {r.critique.map((x, i) => (
              <li key={i}>
                <blockquote className="quote text-pretty">
                  « {x.quote} » <span className="font-display text-xs font-bold tabular">[{x.result}]</span>
                </blockquote>
                {x.why && <p className="mt-1 text-pretty text-muted-foreground">{x.why}</p>}
              </li>
            ))}
          </ul>
          {r.recheck && <p className="mt-3 text-sm font-bold text-pretty">{L.recheck(r.recheck.query, r.recheck.results.length)}</p>}
        </div>
      )}
      {criticDown && <p className="mt-3 text-sm">{L.noCritic}</p>}

      {conf && (
        <div className="mt-5">
          <How conf={conf} />
        </div>
      )}
    </section>
  );
}
