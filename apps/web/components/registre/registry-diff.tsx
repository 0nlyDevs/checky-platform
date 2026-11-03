"use client";

import { useState } from "react";
import { IconMinusCircle, IconQuestion, IconSealCheck, IconWarning, IconXCircle, type Icon } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { ChangedNumber, DiffOp, MatchStatus } from "./types";
import { t } from "@/lib/i18n/live";

const r = t.registre;

// A comparison with the registry is a fact computed by code: ink icons, solid, never verdict colours.
const STATUS_ICON: Record<MatchStatus, Icon> = {
  authentic: IconSealCheck,
  modified: IconWarning,
  not_found: IconQuestion,
  inconsistent: IconXCircle,
  none: IconMinusCircle,
};

/** The registry's answer as an ink icon and a word (« Modifié », « Introuvable »…). */
export function RegistryStatus({ status, className }: { status: MatchStatus; className?: string }) {
  const Glyph = STATUS_ICON[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-display font-extrabold", className)}>
      <Glyph className="size-5 shrink-0" aria-hidden />
      {r.status[status]}
    </span>
  );
}

const KEEP = 8; // words kept on each side of a long identical run
const LONG_DELETE = 24; // a longer run of the original's words missing from the text folds away

function Removed({ text }: { text: string }) {
  return (
    <del className="rounded-sm bg-verdict-false-soft px-0.5 text-verdict-false-ink decoration-2">
      <span className="sr-only">{r.diff.removed} </span>
      {text}
    </del>
  );
}

function Added({ text }: { text: string }) {
  return (
    <ins className="font-bold underline decoration-2 underline-offset-4">
      <span className="sr-only">{r.diff.added} </span>
      {text}
    </ins>
  );
}

function Fold({ label, onOpen, removed }: { label: string; onOpen: () => void; removed?: boolean }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "rounded-sm px-1 text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring",
        removed ? "bg-verdict-false-soft text-verdict-false-ink line-through decoration-2" : "bg-muted text-muted-foreground",
      )}
    >
      {label}
    </button>
  );
}

function Piece({ op, first, last }: { op: DiffOp; first: boolean; last: boolean }) {
  const [open, setOpen] = useState(false);
  if (op.op === "equal") {
    const words = op.a.split(" ");
    const keepHead = last ? KEEP : first ? 0 : KEEP;
    const keepTail = first ? KEEP : last ? 0 : KEEP;
    if (open || words.length <= keepHead + keepTail + 4) return <span>{op.a}</span>;
    const head = words.slice(0, keepHead).join(" ");
    const tail = words.slice(words.length - keepTail).join(" ");
    return (
      <span>
        {head && <>{head} </>}
        <Fold label={r.diff.hidden(words.length - keepHead - keepTail)} onOpen={() => setOpen(true)} />
        {tail && <> {tail}</>}
      </span>
    );
  }
  const removed = op.op === "delete" || op.op === "replace" ? op.a : "";
  const added = op.op === "insert" || op.op === "replace" ? op.b : "";
  const foldRemoved = !open && removed.split(" ").length > LONG_DELETE;
  return (
    <span>
      {removed &&
        (foldRemoved ? (
          <Fold removed label={r.diff.hiddenRemoved(removed.split(" ").length)} onOpen={() => setOpen(true)} />
        ) : (
          <Removed text={removed} />
        ))}
      {removed && added && " "}
      {added && <Added text={added} />}
    </span>
  );
}

/** What changed between a registered original and the text that circulates, word by word: the
 *  original's missing words struck in red, the words the text added underlined. Exported for the
 *  Vérifier crew (slice « crew ») and the dossier. */
export function RegistryDiff({
  diff,
  summary,
  status,
  changedNumbers,
  className,
}: {
  diff: DiffOp[];
  summary?: string | null;
  status?: MatchStatus | null;
  changedNumbers?: ChangedNumber[];
  className?: string;
}) {
  const hasChanges = diff.some((op) => op.op !== "equal");
  return (
    <div className={cn("space-y-3", className)}>
      {(status || summary) && (
        <div>
          {status && <RegistryStatus status={status} className="text-xl" />}
          {summary && <p className="mt-1 max-w-prose text-pretty">{summary}</p>}
        </div>
      )}
      {!!changedNumbers?.length && (
        <div>
          <h4 className="text-sm font-bold">{r.diff.numbers}</h4>
          <ul className="mt-1 space-y-1">
            {changedNumbers.map((n, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 font-display text-lg font-bold tabular-nums">
                {n.original ? (
                  <>
                    <Removed text={n.original} />
                    <span className="font-sans text-sm font-normal text-muted-foreground">{r.diff.becomes}</span>
                    <Added text={n.submitted ?? ""} />
                  </>
                ) : (
                  <>
                    <Added text={n.submitted ?? ""} />
                    <span className="font-sans text-sm font-normal text-muted-foreground">{r.diff.addedNumber}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!!diff.length && (
        <figure className="rounded-md border border-border bg-card p-4">
          <figcaption className="text-sm font-bold">{r.diff.label}</figcaption>
          {hasChanges && <p className="mt-0.5 text-sm text-muted-foreground">{r.diff.legend}</p>}
          <p className="mt-3 leading-8 text-pretty break-words">
            {diff.map((op, i) => (
              <span key={i}>
                {i > 0 && " "}
                <Piece op={op} first={i === 0} last={i === diff.length - 1} />
              </span>
            ))}
          </p>
        </figure>
      )}
    </div>
  );
}
