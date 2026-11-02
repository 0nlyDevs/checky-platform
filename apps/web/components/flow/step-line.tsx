import { IconCheck, IconX } from "@/lib/icons";
import type { ClaimView } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

export const STEPS = ["claim", "evidence", "conclusion"] as const;
export type Step = (typeof STEPS)[number];
export type StepState = "waiting" | "active" | "done" | "suggested" | "failed";

const f = t.flow;

/** Where a dossier stands: the claim is always there; evidence once it has a source; the
 *  conclusion once a journalist confirmed it, or "suggested" while an AI suggestion waits. */
export function claimSteps(c: ClaimView): Record<Step, StepState> {
  // Nobody has picked it up yet: the line waits on 01, whatever was attached on the way in.
  if (c.status === "to_check" && !c.verdict && !c.suggested) return { claim: "active", evidence: "waiting", conclusion: "waiting" };
  const evidence: StepState = c.sources > 0 ? "done" : c.status === "in_progress" ? "active" : "waiting";
  const conclusion: StepState = c.verdict ? "done" : c.suggested ? "suggested" : c.sources > 0 ? "active" : "waiting";
  return { claim: "done", evidence, conclusion };
}

/** The numbered disc: a check once done, the number otherwise; the active one breathes in citron. */
export function StepDisc({ n, state, size, className }: { n: number; state: StepState; size: "lg" | "sm"; className?: string }) {
  const big = size === "lg";
  return (
    <span
      className={cn(
        "relative z-10 grid shrink-0 place-items-center rounded-full font-display font-bold tabular",
        big ? "size-10 text-[0.95rem]" : "size-6 text-[0.7rem]",
        state === "done" && "bg-foreground text-action dark:text-background",
        state === "active" && "step-active bg-action text-action-foreground",
        state === "suggested" && "border-2 border-dashed border-foreground bg-card text-foreground",
        state === "waiting" && "border border-input bg-card text-muted-foreground",
        state === "failed" && "border-2 border-verdict-false bg-card text-verdict-false-ink",
        className,
      )}
    >
      {state === "done" ? (
        <IconCheck className={big ? "size-5" : "size-3.5"} aria-hidden />
      ) : state === "failed" ? (
        <IconX className={big ? "size-5" : "size-3.5"} aria-hidden />
      ) : (
        String(n).padStart(2, "0")
      )}
    </span>
  );
}

/**
 * The signature: 01 L'affirmation, 02 Les éléments, 03 La conclusion, linked by one rule.
 * `full` is the tall version (a live check, the method explained, a dossier); `notes` replace the
 * default explanations (live summaries). `mini` is the compact one on each dossier row.
 */
export function StepLine({
  states,
  notes,
  variant = "full",
  explain = false,
  className,
}: {
  states: Record<Step, StepState>;
  notes?: Partial<Record<Step, React.ReactNode>>;
  variant?: "full" | "mini";
  /** The method explained (nothing is running): every label reads at full strength, no state. */
  explain?: boolean;
  className?: string;
}) {
  if (variant === "mini") {
    return (
      <ol className={cn("flex items-start", className)} aria-label={f.label}>
        {STEPS.map((step, i) => (
          <li key={step} className="relative flex w-[4.25rem] flex-col items-center gap-1" title={`${f.short[step]} · ${f.state[states[step]]}`}>
            {i > 0 && <span aria-hidden className={cn("absolute top-3 right-1/2 h-px w-full", states[step] === "waiting" ? "bg-border" : "bg-foreground")} />}
            <StepDisc n={i + 1} state={states[step]} size="sm" />
            <span className={cn("text-[0.7rem] leading-none", states[step] === "waiting" ? "text-muted-foreground" : "font-bold")}>{f.short[step]}</span>
            <span className="sr-only">{f.state[states[step]]}</span>
          </li>
        ))}
      </ol>
    );
  }
  return (
    <ol className={cn("relative", className)} aria-label={f.label}>
      {STEPS.map((step, i) => (
        <li key={step} className="relative flex gap-4 pb-6 last:pb-0">
          {i < STEPS.length - 1 && (
            <span aria-hidden className={cn("absolute top-10 bottom-0 left-5 w-px", states[STEPS[i + 1]] === "waiting" ? "bg-border" : "bg-foreground")} />
          )}
          <StepDisc n={i + 1} state={states[step]} size="lg" />
          <div className="min-w-0 pt-1.5">
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className={cn("font-display text-[1.05rem] font-bold", !explain && states[step] === "waiting" && "text-muted-foreground")}>{f.steps[step]}</span>
              {!explain && states[step] !== "waiting" && states[step] !== "done" && <span className="text-sm text-muted-foreground">{f.state[states[step]]}</span>}
            </p>
            <div className="mt-0.5 text-sm text-pretty text-muted-foreground">{notes?.[step] ?? f.notes[step]}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}
