import Link from "next/link";
import { IconCalendarDots } from "@/lib/icons";
import { VerdictChip } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { DemoTag, Section } from "./bits";
import type { Meteo } from "./types";

const m = t.rubrique.meteo;

/** Météo des rumeurs: the seasons in effect (from a calendar written by hand) and « Ça revient »,
 *  the verdicts signed around this date in earlier years. */
export function MeteoPanel({ ws, meteo, id = "meteo" }: { ws: string; meteo: Meteo; id?: string }) {
  return (
    <Section id={id} title={m.title} lead={m.lead}>
      {meteo.seasons.length === 0 ? (
        <p className="text-sm text-muted-foreground">{m.empty}</p>
      ) : (
        <ul className="divide-y divide-border">
          {meteo.seasons.map((s) => (
            <li key={s.name} className="py-2.5 first:pt-0">
              <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="inline-flex items-center gap-2 font-bold">
                  <IconCalendarDots className="size-4 shrink-0" aria-hidden />
                  {s.name}
                </span>
                <span className="text-sm text-muted-foreground tabular">{s.days_to != null ? m.electionIn(s.days_to) : m.until(s.until)}</span>
              </p>
              <p className="mt-0.5 text-sm text-pretty text-muted-foreground">{s.note}</p>
            </li>
          ))}
        </ul>
      )}

      <h3 className="mt-5 font-display font-bold">{m.returning}</h3>
      <p className="text-sm text-muted-foreground">{m.returningLead}</p>
      {meteo.returning.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">{m.returningEmpty}</p>
      ) : (
        <ul className="mt-2 space-y-2.5">
          {meteo.returning.map((x) => (
            <li key={x.id} className="text-sm">
              {x.mine ? (
                <Link href={`/w/${ws}/affirmations/${x.id}` as never} className="font-bold text-pretty hover:underline">
                  {x.title}
                </Link>
              ) : x.public ? (
                <Link href={`/verifies/${x.id}` as never} className="font-bold text-pretty hover:underline">
                  {x.title}
                </Link>
              ) : (
                <span className="font-bold">{x.title}</span>
              )}
              <span className="mt-1 flex flex-wrap items-center gap-2">
                <VerdictChip verdict={x.verdict} />
                <span className="text-muted-foreground tabular">{m.seenIn(x.year, x.mine ? t.rubrique.ours : x.newsroom)}</span>
                {x.demo && <DemoTag />}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
