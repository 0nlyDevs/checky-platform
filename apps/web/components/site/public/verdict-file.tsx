import Link from "next/link";
import { VerdictChip } from "@/components/site/fragments";
import { t } from "@/lib/i18n/fr";
import type { PublicVerdict } from "@/lib/public-api";

const p = t.site.pub.file;
const day = (iso: string) => new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });

/** A published verdict as a case card: its stamp, the claim, the newsroom's reason and its sources. */
export function VerdictFile({ v, full = false }: { v: PublicVerdict; full?: boolean }) {
  const label = t.verdict[v.verdict];
  return (
    <article className="pub-file rise" data-observe aria-labelledby={`v-${v.id}`}>
      <div className="t">
        <span>{p.by(v.newsroom.name)}</span>
        <span className="tabular">{v.ref}</span>
      </div>
      <span className="stamp pub-stamp" data-on="true" data-verdict={v.verdict} aria-hidden data-label={label} />
      <p id={`v-${v.id}`} className="pub-claim">
        «&nbsp;{v.title}&nbsp;»
      </p>
      {v.reason && (
        <p className="mt-4 text-lg leading-relaxed">
          <span className="typed text-[15px] text-ink-soft">{p.reason} · </span>
          {v.reason}
        </p>
      )}
      {full && (
        <div className="mt-5">
          <p className="typed text-[15px] text-ink-soft">{p.sources}</p>
          {v.sources.length ? (
            <ul className="mt-1 list-disc space-y-1 pl-5 text-base">
              {v.sources.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-base">{p.noSources}</p>
          )}
          {v.post && <p className="mt-5 bg-index p-4 text-base leading-relaxed">{v.post}</p>}
        </div>
      )}
      <dl className="pub-meta">
        <dt>{p.verdict}</dt>
        <dd>
          <VerdictChip verdict={v.verdict} />
        </dd>
        {v.first_seen_at && (
          <>
            <dt>{p.seen}</dt>
            <dd>{day(v.first_seen_at)}</dd>
          </>
        )}
        <dt>{p.published}</dt>
        <dd>{day(v.published_at)}</dd>
      </dl>
      {!full && (
        <Link href={`/verifies/${v.id}`} className="ulink mt-4 inline-block font-medium">
          {p.open} <span aria-hidden>→</span>
        </Link>
      )}
    </article>
  );
}

/** The archive's row: one file per line, scanned like the index of a filing cabinet. */
export function VerdictRow({ v }: { v: PublicVerdict }) {
  return (
    <li className="pub-row rise" data-observe>
      <Link href={`/verifies/${v.id}`} className="pub-row-link">
        <span className="pub-row-ref">
          <span className="tabular">{v.ref}</span>
          <span>{v.newsroom.name}</span>
          <span>{day(v.published_at)}</span>
        </span>
        <span className="pub-row-claim">
          «&nbsp;{v.title}&nbsp;»
          {v.reason && <span className="pub-row-reason">{v.reason}</span>}
        </span>
        <span className="pub-row-verdict">
          <VerdictChip verdict={v.verdict} />
          <span className="arr" aria-hidden>
            →
          </span>
        </span>
      </Link>
    </li>
  );
}
