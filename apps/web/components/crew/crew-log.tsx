"use client";

import { IconCheck, IconCircleDashed, IconMinus, IconMinusCircle, IconWarning } from "@/lib/icons";
import type { AgentEvent } from "@/components/crew/types";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const l = t.crew.live;

type Member = { name: string; group: "read" | "facts" | "reading"; llm: boolean };

/** The crew in the order it works: the Lecteur, eight fact agents side by side, then the reading. */
export const CREW: Member[] = [
  { name: "Lecteur", group: "read", llm: true },
  ...["Provenance", "Registre", "Chiffres", "Fact-checkers", "Web", "Archives", "Fiabilité", "Ton"].map((name) => ({ name, group: "facts" as const, llm: false })),
  { name: "Éléments", group: "reading", llm: false },
  { name: "Synthèse", group: "reading", llm: true },
  { name: "Contradicteur", group: "reading", llm: true },
  { name: "Confiance", group: "reading", llm: false },
];

function Mark({ status }: { status: AgentEvent["status"] }) {
  const label = <span className="sr-only">{l.status[status] ?? status}</span>;
  if (status === "running")
    return (
      <span className="grid size-4 shrink-0 place-items-center">
        <span className="size-2 animate-pulse rounded-full bg-action" aria-hidden />
        {label}
      </span>
    );
  const Icon = status === "done" ? IconCheck : status === "failed" || status === "timeout" ? IconWarning : status === "skipped" ? IconMinus : status === "no_ai" ? IconMinusCircle : IconCircleDashed;
  return (
    <>
      <Icon className={cn("size-4 shrink-0", status === "done" || status === "failed" || status === "timeout" ? "text-live-foreground" : "text-live-muted")} aria-hidden />
      {label}
    </>
  );
}

/**
 * The crew racing, in the ink panel: every agent as it starts and ends, with its time. Facts found
 * by code sit in a solid frame, readings by a model in a dashed one (and say « IA »).
 */
export function CrewLog({ agents, runs, running }: { agents: Record<string, AgentEvent>; runs: Record<string, number>; running: boolean }) {
  const known = new Set(CREW.map((m) => m.name));
  const extra: Member[] = Object.values(agents)
    .filter((a) => !known.has(a.agent))
    .map((a) => ({ name: a.agent, group: "reading", llm: !!a.llm }));
  const members = [...CREW, ...extra];
  const groups = (["read", "facts", "reading"] as const).map((g) => ({ g, list: members.filter((m) => m.group === g) }));

  return (
    <section className="@container rounded-md bg-live p-4 text-live-foreground" aria-label={l.title}>
      <h2 className="flex items-center justify-between gap-3 font-display text-sm font-bold">
        {l.title}
        <span className="flex items-center gap-1.5 text-xs font-bold">
          <span className={cn("size-2 rounded-full", running ? "animate-pulse bg-action" : "bg-live-muted")} aria-hidden />
          {running ? l.running : l.done}
        </span>
      </h2>
      {groups.map(({ g, list }) => (
        <div key={g} className="mt-3">
          <h3 className="text-xs font-bold text-live-muted">{l.stages[g]}</h3>
          <ol className={cn("mt-1.5 grid gap-1.5", g === "facts" && "@md:grid-cols-2")}>
            {list.map((m) => {
              const a = agents[m.name];
              const status = a?.status ?? "waiting";
              return (
                <li
                  key={m.name}
                  className={cn(
                    "rounded-[3px] border px-2.5 py-1.5 transition-colors",
                    m.llm ? "border-dashed" : "border-solid",
                    status === "running" ? "border-live-foreground" : "border-live-muted/60",
                    status !== "waiting" && "arrive",
                  )}
                >
                  <div className="flex items-center gap-2 text-sm">
                    <Mark status={status} />
                    <span className="min-w-0 truncate font-bold">{m.name}</span>
                    {m.llm && <span className="rounded-sm border border-dashed border-live-muted px-1 text-[0.6875rem] leading-4 font-bold">{l.model}</span>}
                    {(runs[m.name] ?? 0) > 1 && <span className="text-xs text-live-muted">{l.again}</span>}
                    <span className="ml-auto shrink-0 text-xs text-live-muted tabular">{a?.ms !== undefined ? l.seconds(a.ms) : l.status[status]}</span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-xs text-pretty text-live-muted">{a?.summary || l.roles[m.name] || ""}</p>
                </li>
              );
            })}
          </ol>
        </div>
      ))}
      <p className="mt-3 text-xs text-pretty text-live-muted">{l.legend}</p>
    </section>
  );
}
