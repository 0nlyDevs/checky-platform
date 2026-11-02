import type { Verdict } from "@fanilo/shared";
import { Check, CircleDashed, Copy, FileText, ImageIcon, Link2, Mic, Sparkles } from "lucide-react";
import { VERDICT_META } from "@/components/claims/verdict";
import { LogoMark } from "@/components/brand/logo";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

// Pieces of the real product shown on the landing, at true size, marked data-ui: the app's own
// lines, radius and verdict colours (Grille d'antenne). Content is the page's fictional rumour.

const f = t.site.method.frag;
const o = t.site.outputs;
const claims = t.site.claims;
const lead = claims[0];
const START = 22 * 60; // the grid runs 22:00 → 07:40, "maintenant"
const SPAN = 9 * 60 + 40;
const place = (minutes: number) => (((minutes - START + 1440) % 1440) / SPAN) * 100;
const at = (time: string) => {
  const [h, m] = time.split(":").map(Number);
  return place(h * 60 + m);
};
const NOW = 100;

function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div data-ui className={cn("rounded-md border border-border bg-card text-[0.9375rem] leading-snug text-foreground", className)}>
      {children}
    </div>
  );
}

/** The product's own header line: mark, workspace, and what the panel is about. */
function Bar({ right }: { right?: React.ReactNode }) {
  return (
    <div data-ui className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm text-muted-foreground">
      <LogoMark className="size-5" />
      <span className="font-medium text-foreground">{brand.name}</span>
      <span>· {f.desk}</span>
      {right && <span className="ml-auto">{right}</span>}
    </div>
  );
}

export function VerdictChip({ verdict, className }: { verdict: Verdict; className?: string }) {
  const m = VERDICT_META[verdict];
  const Icon = m.icon;
  return (
    <span
      data-ui
      className={cn(
        "inline-flex flex-none items-center gap-1.5 rounded-sm px-2 py-0.5 text-sm font-medium whitespace-nowrap",
        m.soft,
        m.ink,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {m.label}
    </span>
  );
}

/** Step 1: the day grid, the claim of the story selected. */
export function GridFragment() {
  return (
    <Panel className="w-[min(32rem,100%)]">
      <Bar right={<span className="tabular">{f.now} 07:40</span>} />
      <div className="px-4 pt-3 pb-4">
        {/* Each hour label stands over its own time on the grid. */}
        <div className="relative ml-20 h-5 font-display text-sm tracking-wide text-muted-foreground tabular">
          {f.hours.map((h) => (
            <span key={h} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${place(parseInt(h, 10) * 60)}%` }}>
              {h}
            </span>
          ))}
        </div>
        <ul className="mt-2 space-y-1.5">
          {claims.map((c, i) => {
            const from = at(c.time);
            const m = VERDICT_META[c.verdict as Verdict];
            const selected = i === 0;
            return (
              <li key={c.ref} className={cn("flex h-7 items-center gap-3 rounded-sm", selected && "bg-muted")}>
                <span
                  className={cn(
                    "w-17 flex-none pl-1.5 font-display text-base tracking-wide tabular",
                    selected ? "font-medium text-foreground" : "text-muted-foreground",
                  )}
                >
                  {c.ref}
                </span>
                <span className="relative h-4 flex-1">
                  <span
                    data-ui className={cn("absolute inset-y-0 rounded-[3px]", selected ? "border border-foreground bg-transparent" : m.fill)}
                    style={{ left: `${from}%`, width: `${NOW - from}%` }}
                  />
                </span>
              </li>
            );
          })}
        </ul>
        <div data-ui className="mt-4 flex items-start gap-3 border-t border-border pt-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-muted-foreground tabular">
              {lead.ref} · vue à {lead.time} · {t.origins[lead.origin as keyof typeof t.origins]}
            </p>
            <p className="mt-1 font-medium text-foreground">{lead.title}</p>
          </div>
          <span className="inline-flex flex-none items-center gap-1.5 text-sm text-foreground">
            <CircleDashed className="size-4" aria-hidden />
            {t.status.to_check}
          </span>
        </div>
      </div>
    </Panel>
  );
}

const SOURCE_ICON = { link: Link2, audio: Mic, image: ImageIcon, pdf: FileText } as const;

/** Step 2: the evidence attached to the claim, a voice note transcribed. */
export function SourcesFragment() {
  return (
    <Panel className="w-[min(32rem,100%)]">
      <Bar right={f.sourcesTitle} />
      <ul data-ui className="divide-y divide-border">
        {f.sources.map((s) => {
          const Icon = SOURCE_ICON[s.kind as keyof typeof SOURCE_ICON];
          return (
            <li key={s.title} className="flex gap-3 px-4 py-3">
              <Icon className="mt-0.5 size-4 flex-none text-muted-foreground" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-foreground">{s.title}</p>
                <p className="text-sm text-muted-foreground">{s.meta}</p>
                {s.kind === "audio" && (
                  <p className="mt-2 flex gap-2.5 text-sm text-foreground">
                    <span className="text-primary tabular">{f.transcript.time}</span>
                    {f.transcript.text}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

/** Step 3: the AI's suggestion stays dashed; the quote was found word for word in its source. */
export function AnalysisFragment() {
  const m = VERDICT_META.false;
  return (
    <Panel className="w-[min(32rem,100%)]">
      <Bar right={lead.ref} />
      <div className="space-y-3 p-4">
        <p data-ui className={cn("flex items-center gap-2 rounded-sm border border-dashed border-current px-3 py-2 font-medium", m.soft, m.ink)}>
          <Sparkles className="size-4 flex-none" aria-hidden />
          {f.suggestion}
        </p>
        <figure>
          <blockquote className="text-pretty text-foreground">{f.quote}</blockquote>
          <figcaption className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
            <Link2 className="size-3.5 flex-none" aria-hidden />
            {f.quoteSource}
          </figcaption>
        </figure>
        <p data-ui className="border-t border-border pt-3 text-sm text-muted-foreground">{f.kept}</p>
      </div>
    </Panel>
  );
}

/** Step 4: the journalist's choice, confirmed. */
export function PublishFragment() {
  return (
    <Panel className="w-[min(32rem,100%)]">
      <Bar right={lead.ref} />
      <div className="p-4">
        <p className="font-medium text-foreground">{lead.title}</p>
        <div role="presentation" className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(["true", "misleading", "false", "unverifiable"] as const).map((v) => {
            const vm = VERDICT_META[v];
            const Icon = vm.icon;
            const active = v === "false";
            return (
              <span
                key={v}
                className={cn(
                  "flex h-9 items-center justify-center gap-1.5 rounded-sm border text-sm font-medium",
                  active ? cn(vm.fill, vm.on, "border-transparent") : cn("border-border", vm.ink),
                )}
              >
                <Icon className="size-3.5" aria-hidden />
                {vm.label}
              </span>
            );
          })}
        </div>
        <p className="mt-3 flex items-center gap-2 text-sm text-foreground">
          <Check className="size-4 flex-none text-verdict-true-ink" aria-hidden />
          {f.confirmed}
        </p>
      </div>
    </Panel>
  );
}

/** Outputs (what leaves at 7 a.m.): each one as the product makes it. */
export function CardSheet() {
  const m = VERDICT_META.false;
  const Icon = m.icon;
  // The shared card keeps its fixed palette (verdict-card.tsx), the same in every theme.
  return (
    <div data-ui className="w-[min(30rem,100%)] bg-[#f4f6f5] text-[#14201d]">
      <div className="flex items-center gap-2.5 bg-[#0f3b36] px-5 py-3 text-white">
        <LogoMark className="size-6" />
        <span className="font-semibold">{brand.name}</span>
        <span className="ml-auto text-sm opacity-85">{o.card.checked}</span>
      </div>
      <div className="space-y-4 px-5 py-6">
        <span className="inline-flex items-center gap-2.5 rounded-[5px] bg-[#c43d32] px-3 py-2 text-white">
          <Icon className="size-6" aria-hidden />
          <span className="text-2xl leading-none font-semibold uppercase">{m.label}</span>
        </span>
        <div>
          <p className="text-sm text-[#4b5a56]">{o.card.claim}</p>
          <p className="mt-1 text-xl leading-snug font-semibold text-pretty">« {lead.title} »</p>
        </div>
        <p className="leading-relaxed text-pretty">{o.card.reason}</p>
        <p className="text-sm text-[#4b5a56]">{o.card.sources}</p>
      </div>
      <div data-ui className="mx-5 border-t border-[#c9d3d0] py-3 text-sm font-semibold tabular">{lead.ref}</div>
    </div>
  );
}

export function PostSheet() {
  return (
    <Panel className="w-[min(30rem,100%)]">
      <Bar right={o.post.label} />
      <div className="p-5">
        <p className="leading-relaxed text-pretty text-foreground">{o.post.text}</p>
        <div data-ui className="mt-4 flex items-center justify-between border-t border-border pt-3 text-sm text-muted-foreground">
          <span>{o.post.meta}</span>
          <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
            <Copy className="size-4" aria-hidden />
            {o.post.copy}
          </span>
        </div>
      </div>
    </Panel>
  );
}

export function QuotesSheet() {
  return (
    <Panel className="w-[min(30rem,100%)]">
      <Bar right={o.quotes.label} />
      <ul data-ui className="divide-y divide-border">
        {o.quotes.items.map((q) => (
          <li key={q.time} className="flex gap-3 px-5 py-3">
            <span className="text-primary tabular">{q.time}</span>
            <span className="text-pretty text-foreground">{q.text}</span>
          </li>
        ))}
      </ul>
      <p data-ui className="border-t border-border px-5 py-3 text-sm text-muted-foreground">{o.quotes.claim}</p>
    </Panel>
  );
}

export function AnalysisSheet() {
  return (
    <Panel className="w-[min(30rem,100%)]">
      <Bar right={o.analysis.label} />
      <div className="space-y-4 p-5">
        <div className="flex items-start gap-3">
          <VerdictChip verdict="false" />
          <p className="text-pretty text-foreground">{o.analysis.reason}</p>
        </div>
        <ul className="space-y-3">
          {o.analysis.evidence.map((e) => (
            <li key={e.source}>
              <p className="text-pretty text-foreground">{e.text}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {e.stance} · {e.source}
              </p>
            </li>
          ))}
        </ul>
        <p data-ui className="border-t border-border pt-3 text-sm text-muted-foreground">{o.analysis.dropped}</p>
      </div>
    </Panel>
  );
}
