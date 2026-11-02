import Link from "next/link";
import { research as t } from "@/lib/i18n/fr/research";

export type AgentEvent = { agent: string; status: keyof typeof t.status; summary?: string; ms?: number; llm?: boolean };
export type ResearchExtras = {
  audit?: { score: number; checked_at: string; components: { key: keyof typeof t.components; points: number; maximum: number; count: number }[]; not_read: number[]; undated: number[]; similar_wording: number[][] };
  transparency?: { author: string | null; published_at: string | null };
  framing?: { kind: keyof typeof t.kinds; quote: string; explanation: string; target: string }[];
  critique?: { result: number; quote: string; why: string }[];
  trace?: AgentEvent[];
  registry?: { status: keyof typeof t.registryStates; title?: string; url?: string; is_demo?: boolean; changes?: { operation: string; original: string; submitted: string }[] };
};

export function AgentTrace({ agents }: { agents: AgentEvent[] }) {
  if (!agents.length) return null;
  return <section className="mt-6 border-y border-border py-4" aria-label={t.trace}>
    <h2 className="font-display text-lg font-bold">{t.trace}</h2>
    <ul className="mt-2 divide-y divide-border text-sm">{agents.map(a => <li key={a.agent} className="flex flex-wrap justify-between gap-2 py-2">
      <span className="font-semibold">{a.agent}</span><span>{t.status[a.status] ?? a.status}{a.ms !== undefined ? ` · ${(a.ms / 1000).toFixed(1)} s` : ""}</span>
      {a.summary && <span className="w-full text-muted-foreground">{a.summary}</span>}
    </li>)}</ul>
  </section>;
}

export function ResearchDetails({ data, ws }: { data: ResearchExtras; ws: string }) {
  const audit = data.audit;
  return <section className="space-y-5 border-t border-border pt-5">
    <h2 className="font-display text-2xl font-bold">{t.title}</h2>
    {audit && <div>
      <p className="font-display text-xl font-bold">{audit.score} % · {t.score}</p>
      <p className="mt-2 max-w-prose text-sm text-muted-foreground">{t.scoreHelp}</p>
      <time className="mt-2 block text-sm" dateTime={audit.checked_at}>{new Date(audit.checked_at).toLocaleString("fr-FR")}</time>
      <details className="mt-3 rounded-md border border-border p-3"><summary className="cursor-pointer font-semibold">{t.formula}</summary>
        <ul className="mt-3 space-y-2 text-sm">{audit.components.map(c => <li key={c.key}>{t.components[c.key]} : {c.count} · {c.points}/{c.maximum}</li>)}</ul>
        <p className="mt-3 text-sm">{t.calculation}</p><p className="mt-2 text-sm text-muted-foreground">{t.independence}</p>
        {!!audit.similar_wording.length && <p className="mt-2 text-sm">{t.repeated} : {audit.similar_wording.map(p => p.map(n => `[${n}]`).join(" ↔ ")).join(", ")}</p>}
      </details>
    </div>}
    {data.transparency && <details className="rounded-md border border-border p-3"><summary className="cursor-pointer font-semibold">{t.transparency}</summary>
      <dl className="mt-3 text-sm"><dt className="font-bold">{t.author}</dt><dd>{data.transparency.author || t.unknown}</dd><dt className="mt-2 font-bold">{t.date}</dt><dd>{data.transparency.published_at || t.unknown}</dd></dl>
      <p className="mt-2 text-sm text-muted-foreground">{t.publisher}</p>
    </details>}
    {!!data.framing?.length && <div className="rounded-md border border-dashed border-border p-4">
      <h3 className="font-bold">{t.framing}</h3><p className="mt-1 text-sm text-muted-foreground">{t.framingHelp}</p>
      <ul className="mt-3 space-y-4">{data.framing.map((s, i) => <li key={i}><p className="text-sm font-bold">{t.kinds[s.kind]}</p><blockquote className="mt-1 border-l-2 border-border pl-3">« {s.quote} »</blockquote><p className="mt-1 text-sm">{s.explanation}</p></li>)}</ul>
    </div>}
    {!!data.critique?.length && <div className="rounded-md border border-dashed border-border p-4"><h3 className="font-bold">{t.critique}</h3>
      <ul className="mt-2 space-y-3">{data.critique.map((c, i) => <li key={i}><blockquote>« {c.quote} » [{c.result}]</blockquote><p className="mt-1 text-sm">{c.why}</p></li>)}</ul>
    </div>}
    {data.trace?.some(a => a.agent === "Contradicteur" && ["timeout", "failed"].includes(a.status)) && <p role="status" className="text-sm">{t.noCritic}</p>}
    {data.registry && <details className="rounded-md border border-border p-3"><summary className="cursor-pointer font-semibold">{t.registry} · {t.registryStates[data.registry.status]}</summary>
      <p className="mt-2 text-sm text-muted-foreground">{t.registryHelp}</p>
      {data.registry.title && <p className="mt-2 font-semibold">{data.registry.is_demo && `${t.demo} · `}{data.registry.title}</p>}
      <div className="mt-3 space-y-2">{data.registry.changes?.filter(c => c.operation !== "equal").map((c, i) => <div key={i} className="border-l-2 border-border pl-3 text-sm">
        {c.original && <p>{t.original} : <span className="font-semibold">{c.original}</span></p>}{c.submitted && <p>{t.submitted} : <del>{c.submitted}</del></p>}
      </div>)}</div>
    </details>}
    <div className="border-t border-border pt-4"><h3 className="font-bold">{t.contact}</h3><p className="mt-1 text-sm text-muted-foreground">{t.contactHelp}</p><Link href={`/w/${ws}/annuaire`} className="mt-2 inline-block font-semibold underline underline-offset-4">{t.openDirectory}</Link></div>
  </section>;
}
