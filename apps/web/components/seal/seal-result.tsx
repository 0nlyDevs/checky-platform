"use client";

import { VERDICT_META } from "@/components/claims/verdict";
import { useDay, useMoment, useT } from "@/lib/i18n";
import { IconQuestion, IconSealCheck, IconWarning, IconXCircle, type Icon } from "@/lib/icons";
import { checkNumber, type SealCheck } from "@/lib/seal";
import { cn } from "@/lib/utils";

const isVerdict = (v: unknown): v is keyof typeof VERDICT_META => typeof v === "string" && v in VERDICT_META;
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

/** The answer, word and icon (never colour alone): Authentique, Ne correspond pas, Clé révoquée. */
export function SealStatus({ check, className }: { check: SealCheck; className?: string }) {
  const s = useT().offline.seal;
  const day = useDay();
  const issuer = check.kind === "verdict" ? (check.key?.newsroom.name ?? "") : str(check.payload?.issuer) || (check.key?.issuer ?? "");
  const [Glyph, title, lead]: [Icon, string, string] =
    check.status === "authentic"
      ? [IconSealCheck, s.authentic, s.authenticLead(issuer)]
      : check.status === "revoked"
        ? [IconWarning, s.revoked, check.revoked ? s.revokedLead(day(check.revoked.revoked_at)) : s.revokedLeadNoDate]
        : check.status === "unknown_key"
          ? [IconQuestion, s.unknown, s.unknownLead]
          : check.status === "unsupported"
            ? [IconQuestion, s.unknown, s.unsupported]
            : [IconXCircle, s.mismatch, s.mismatchLead];
  return (
    <div role="status" data-seal={check.status} className={cn("verdict-land rounded-md border-2 border-foreground bg-card p-5", className)}>
      <p className="flex items-center gap-2 font-display text-3xl font-extrabold tracking-tight">
        <Glyph className="size-8 shrink-0" aria-hidden />
        {title}
      </p>
      <p className="mt-2 max-w-prose text-lg text-pretty">{lead}</p>
    </div>
  );
}

/** What the seal signed, read from the QR itself, to compare with the paper in hand. */
export function SignedFields({ check }: { check: SealCheck }) {
  const t = useT();
  const s = t.offline.seal;
  const c = t.registre.check;
  const day = useDay();
  const moment = useMoment();
  const p = check.payload;
  if (!p) return null;
  const rows: [string, React.ReactNode][] = [];
  if (check.kind === "communique") {
    rows.push([c.issuer, str(p.issuer)]);
    rows.push([c.number, p.number ? `N° ${str(p.number)}` : "—"]);
    rows.push([c.date, p.issued_on ? day(str(p.issued_on)) : "—"]);
    rows.push([c.titleField, str(p.title)]);
  } else {
    const verdict = isVerdict(p.verdict) ? p.verdict : null;
    const meta = verdict ? VERDICT_META[verdict] : null;
    const n = checkNumber(p.ref);
    rows.push([s.titleField, `« ${str(p.title)} »`]);
    if (meta && verdict) {
      const Glyph = meta.icon;
      rows.push([
        s.verdictWord,
        <span key="v" className="inline-flex items-center gap-1.5">
          <Glyph className="size-5" aria-hidden />
          {t.verdict[verdict]}
        </span>,
      ]);
    }
    rows.push([s.number, n !== null ? `${str(p.ref)} · ${s.checkLabel(n)}` : str(p.ref) || "—"]);
    rows.push([s.signedAt, p.signed_at ? moment(str(p.signed_at).replace(/Z$/, ":00Z")) : "—"]);
  }
  return (
    <dl className="grid gap-x-8 gap-y-4 rounded-md border border-border bg-card p-4 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className={cn(label === c.titleField || label === s.titleField ? "sm:col-span-2" : "")}>
          <dt className="text-sm text-muted-foreground">{label}</dt>
          <dd className="font-display text-xl font-bold text-pretty tabular-nums">{value}</dd>
        </div>
      ))}
      {check.kind === "communique" && p.fingerprint ? (
        <div className="sm:col-span-2">
          <dt className="text-sm text-muted-foreground">{c.fingerprint}</dt>
          <dd className="font-mono text-xs break-all">{str(p.fingerprint)}</dd>
        </div>
      ) : null}
    </dl>
  );
}
