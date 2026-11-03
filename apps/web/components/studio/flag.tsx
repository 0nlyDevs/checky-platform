import type { ShowClaim } from "@checky/shared";
import { VerdictChip } from "@/components/claims/verdict";
import { IconCheckCircle, IconCircleDashed, IconWarning, type Icon } from "@/lib/icons";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";
import type { Verdict } from "@checky/shared";

const f = t.studio.flag;

export type FlagKind = "consistent" | "contradicted" | "no_source";

/** One piece of what the claim was compared with (figure, registry original, signed verdict). */
export type Evidence = {
  type: "figure" | "registry" | "verdict";
  stance: "consistent" | "contradicted" | "related" | "none";
  title?: string;
  official?: string;
  claimed?: string;
  source?: string | null;
  number?: string | null;
  date?: string | null;
  date_label?: string;
  url?: string | null;
  ref?: string | null;
  verdict?: Verdict;
  item_id?: string | null;
  changed?: { original: string | null; submitted: string }[];
  summary?: string;
  old?: boolean;
  demo?: boolean;
};

export function flagOf(claim: Pick<ShowClaim, "flag">): { kind: FlagKind; evidence: Evidence[] } {
  const flag = (claim.flag ?? {}) as { kind?: FlagKind; evidence?: Evidence[] };
  return { kind: flag.kind ?? "no_source", evidence: flag.evidence ?? [] };
}

// Flags are never verdicts: ink icons and words, no verdict colour.
const FLAG_ICON: Record<FlagKind, Icon> = {
  consistent: IconCheckCircle,
  contradicted: IconWarning,
  no_source: IconCircleDashed,
};

export function FlagLabel({ kind, className, large = false }: { kind: FlagKind; className?: string; large?: boolean }) {
  const Glyph = FLAG_ICON[kind];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-bold",
        kind === "no_source" ? "rounded-full border border-dashed border-foreground px-2.5 py-0.5" : "rounded-full border border-foreground px-2.5 py-0.5",
        large ? "text-2xl" : "text-sm",
        className,
      )}
    >
      <Glyph className={large ? "size-7" : "size-4"} aria-hidden />
      {f.kinds[kind]}
    </span>
  );
}

/** « Contredit par « Hausse du tarif » : +12 % » — what was compared, said in words. */
export function evidenceTitle(e: Evidence): string {
  if (e.type === "figure") {
    return e.stance === "consistent" ? f.figureConsistent(e.title ?? "", e.official ?? "") : f.figureContradicted(e.title ?? "", e.official ?? "");
  }
  if (e.type === "registry") {
    const who = e.source ?? "";
    if (e.stance === "consistent") return f.registryConsistent(who, e.number ?? null);
    if (e.stance === "contradicted") return f.registryContradicted(who, e.number ?? null);
    if (e.stance === "related") return f.registryRelated(who, e.number ?? null);
    return e.summary ?? f.registryNone;
  }
  const ref = e.ref ?? e.title ?? "";
  if (e.stance === "consistent") return f.verdictConsistent(ref);
  if (e.stance === "contradicted") return f.verdictContradicted(ref);
  return f.verdictNoted(ref);
}

export function EvidenceLine({ e, className, large = false }: { e: Evidence; className?: string; large?: boolean }) {
  const source = e.type === "registry" && e.stance === "none" ? "" : f.source(e.source ?? "", e.date_label ?? "");
  return (
    <div className={cn("min-w-0", className)}>
      <p className={cn("text-pretty", large ? "text-xl font-bold" : "font-bold")}>{evidenceTitle(e)}</p>
      <p className={cn("mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground", large ? "text-lg" : "text-sm")}>
        {source && <span>{source}</span>}
        {e.type === "verdict" && e.verdict && <VerdictChip verdict={e.verdict} />}
        {e.old && <span>· {f.old}</span>}
        {e.demo && <span className="rounded-sm border border-border px-1.5 text-xs">{t.studio.demo}</span>}
      </p>
      {e.changed?.map((c, i) => (
        <p key={i} className={cn("mt-0.5", large ? "text-lg" : "text-sm")}>
          {f.changed(c.original ?? "", c.submitted)}
        </p>
      ))}
    </div>
  );
}

/** The follow-up question code proposes for a flag; the producer edits it before sending. */
export function questionFor(claim: Pick<ShowClaim, "flag">): string {
  const { kind, evidence } = flagOf(claim);
  const q = t.studio.questions;
  const first = evidence[0];
  if (kind === "contradicted" && first) {
    if (first.type === "figure") return q.figure(first.official ?? "", f.source(first.source ?? "", first.date_label ?? ""), first.claimed ?? "");
    if (first.type === "registry") return q.registry(first.source ?? "");
    return q.verdict(first.ref ?? "");
  }
  if (kind === "consistent" && first) return q.consistent(first.source ?? "");
  return q.noSource;
}
