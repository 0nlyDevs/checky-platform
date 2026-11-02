import { IconCheck, IconMinus, IconQuestion, IconWarning } from "@/lib/icons";
import type { Credibility, CrewResult, Framing, Risk, Tone } from "@/components/crew/types";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const k = t.crew;

/** « Fiabilité de la source »: what the site shows about itself, signal by signal, never a score. */
export function Reliability({ c }: { c: Credibility }) {
  const R = k.reliability;
  return (
    <section className="rounded-md border border-border bg-card p-5">
      <h2 className="font-display text-lg font-bold">{R.title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{R.lead}</p>
      <p className="mt-3 flex flex-wrap items-center gap-2">
        <span className="font-bold">{c.name ?? c.domain}</span>
        {c.known && <span className="rounded-sm bg-foreground px-1.5 py-px text-xs font-bold text-background">{R.known[c.known]}</span>}
      </p>
      {c.platform && <p className="mt-1 text-sm text-pretty text-muted-foreground">{R.platform(c.platform)}</p>}
      <dl className="mt-3 grid gap-px overflow-hidden rounded-[3px] border border-border bg-border sm:grid-cols-2">
        {c.signals.map((s) => {
          const Icon = s.status === "found" ? IconCheck : s.status === "missing" ? IconMinus : IconQuestion;
          return (
            <div key={s.key} className="bg-card px-3 py-2">
              <dt className="text-xs text-muted-foreground">{R.keys[s.key] ?? s.key}</dt>
              <dd className={cn("mt-0.5 flex items-center gap-1.5 text-sm font-bold", s.status === "unknown" && "font-normal")}>
                <Icon className="size-4 shrink-0" aria-hidden />
                {R.status[s.status] ?? s.status}
              </dd>
              {s.detail && <dd className="mt-0.5 text-xs text-pretty text-muted-foreground">{s.detail}</dd>}
            </div>
          );
        })}
      </dl>
    </section>
  );
}

/** How the message is written (code), and the framing the Lecteur saw (AI, dashed). */
export function ToneCard({ tone, framing }: { tone?: Tone; framing?: Framing[] }) {
  const T = k.tone;
  if (!tone && !framing?.length) return null;
  return (
    <section className="rounded-md border border-border bg-card p-5">
      <h2 className="font-display text-lg font-bold">{T.title}</h2>
      {tone && (
        <>
          <p className="mt-1 font-display text-2xl font-extrabold">{T.level[tone.level] ?? tone.level}</p>
          {!!tone.signals.length && (
            <ul className="mt-2 space-y-1.5 text-sm">
              {tone.signals.map((s, i) => (
                <li key={i} className="text-pretty">
                  <span className="font-bold">{T.kinds[s.kind] ?? s.kind}</span> · <span className="quote text-muted-foreground">« {s.quote} »</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted-foreground">{T.note}</p>
        </>
      )}
      {!!framing?.length && (
        <div className="mt-4 rounded-md border border-dashed border-foreground/40 p-3">
          <h3 className="text-sm font-bold">{T.framing}</h3>
          <ul className="mt-2 space-y-2.5 text-sm">
            {framing.map((f, i) => (
              <li key={i}>
                <p className="font-bold">{T.framingKinds[f.kind] ?? f.kind}</p>
                <blockquote className="quote text-pretty text-muted-foreground">« {f.quote} »</blockquote>
                {f.explanation && <p className="text-pretty">{f.explanation}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** « Risque élevé »: an ink warning, never a verdict colour; the reasons quote the message. */
export function RiskNote({ risk }: { risk?: Risk }) {
  if (!risk || risk.level === "low") return null;
  const R = k.risk;
  return (
    <div className="mt-4 border-t border-border pt-4">
      <p className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-sm font-bold", risk.level === "high" ? "border-foreground" : "border-border")}>
        <IconWarning className="size-4 shrink-0" aria-hidden />
        {R.label[risk.level]}
      </p>
      {!!risk.reasons.length && (
        <ul className="mt-2 space-y-1 text-sm">
          {risk.reasons.map((x, i) => (
            <li key={i} className="text-pretty">
              <span className="font-bold">{R.kinds[x.kind] ?? x.kind}</span> · <span className="quote text-muted-foreground">« {x.quote} »</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1.5 text-xs text-muted-foreground">{R.note}</p>
    </div>
  );
}

/** Who sees what: the public sees what was already published, then the signed verdict; never the reading. */
export function PublicStrip({ r }: { r: CrewResult }) {
  const S = k.strip;
  const rows: [string, string][] = [
    [S.already, S.alreadyValue(r.fact_checks?.length ?? 0, r.published?.length ?? 0)],
    [S.after, S.afterValue],
    [S.never, S.neverValue],
  ];
  return (
    <section aria-label={S.label} className="rounded-md border border-border bg-card px-4 py-3 text-sm">
      <dl className="flex flex-wrap gap-x-2 gap-y-1">
        {rows.map(([label, value], i) => (
          <div key={label} className="inline">
            <dt className="inline font-bold">{label} :</dt> <dd className="inline">{value}</dd>
            {i < rows.length - 1 && (
              <span className="ml-2 text-muted-foreground" aria-hidden>
                ·
              </span>
            )}
          </div>
        ))}
      </dl>
    </section>
  );
}
