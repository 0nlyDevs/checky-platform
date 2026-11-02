import { VERDICT_META } from "@/components/claims/verdict";
import { StepLine } from "@/components/flow/step-line";
import { t } from "@/lib/i18n/fr";

const s = t.site.home.specimen;
const m = VERDICT_META.misleading;

/** The message with the phrases Checky flags lit one after the other, as on the Vérifier screen. */
function Marked({ text, quotes }: { text: string; quotes: readonly string[] }) {
  const parts: React.ReactNode[] = [];
  let rest = text;
  quotes.forEach((q, i) => {
    const at = rest.indexOf(q);
    if (at < 0) return;
    parts.push(rest.slice(0, at));
    parts.push(
      <mark key={q} className="signal-mark" style={{ "--i": i } as React.CSSProperties}>
        {q}
      </mark>,
    );
    rest = rest.slice(at + q.length);
  });
  parts.push(rest);
  return <>{parts}</>;
}

/**
 * One fictional rumour, worked through: the message as received, the phrases that raise doubt, the
 * three steps, and the verdict the newsroom confirmed. It plays once, the way Checky works.
 */
export function Specimen() {
  const Icon = m.icon;
  return (
    <figure className="rounded-md border border-border bg-card p-4 md:p-6" aria-label={s.label}>
      <figcaption className="flex items-center justify-between gap-3 text-sm">
        <span className="rounded-sm border border-foreground px-1.5 py-px font-bold">{s.label}</span>
        <span className="text-muted-foreground">{s.received}</span>
      </figcaption>
      <blockquote className="mt-4 rounded-md bg-muted p-4 text-lg leading-relaxed text-pretty">
        <Marked text={s.message} quotes={s.quotes} />
      </blockquote>
      <div className="arrive mt-6" style={{ "--i": 8 } as React.CSSProperties}>
        <StepLine states={{ claim: "done", evidence: "done", conclusion: "done" }} notes={{ claim: s.claim, evidence: s.evidence, conclusion: t.site.pub.file.confirmed }} />
      </div>
      <div className={`verdict-land mt-5 rounded-md border-2 border-current p-4 ${m.soft} ${m.ink}`} style={{ animationDelay: "1.5s" }}>
        <p className="flex items-center gap-2.5 font-display text-4xl font-extrabold tracking-tight">
          <Icon className="size-9 shrink-0" strokeWidth={2.4} aria-hidden />
          {m.label}
        </p>
        <p className="mt-2 text-pretty text-foreground">{s.reason}</p>
      </div>
    </figure>
  );
}
