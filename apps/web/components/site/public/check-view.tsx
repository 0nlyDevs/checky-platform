"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { VerdictFile, VerdictRow } from "@/components/site/public/verdict-file";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, publicApi } from "@/lib/public-api";

const c = t.site.pub.check;
const a = t.site.pub.archive;

/** "Is it already checked?" over the archive of published verdicts, then the latest verdicts. */
export function CheckView() {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<PublicVerdict[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [page, setPage] = useState<{ items: PublicVerdict[]; total: number } | null>(null);
  const [limit, setLimit] = useState(9);

  useEffect(() => {
    const id = setTimeout(() => {
      publicApi<{ items: PublicVerdict[]; total: number }>(`/verdicts?limit=${limit}${q ? `&q=${encodeURIComponent(q)}` : ""}`)
        .then(setPage)
        .catch(() => setPage({ items: [], total: 0 }));
    }, 250);
    return () => clearTimeout(id);
  }, [q, limit]);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    if (text.trim().length < 3) return;
    setBusy(true);
    try {
      const res = await publicApi<{ score: number; verdict: PublicVerdict }[]>("/match", { method: "POST", body: JSON.stringify({ text }) });
      setHits(res.map((r) => r.verdict));
    } catch {
      setHits([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="frame-x pt-[clamp(32px,6vw,72px)] pb-[clamp(64px,8vw,110px)]" aria-labelledby="check-title">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:items-end">
          <div>
            <h1 id="check-title" className="disp text-[clamp(52px,8vw,128px)] leading-[0.88]">
              {c.title}
            </h1>
            <p className="mt-6 max-w-[46ch] text-xl leading-relaxed">{c.lead}</p>
          </div>
          <form onSubmit={check} className="dossier-card" aria-label={c.title}>
            <label htmlFor="check-text" className="!mt-0">
              {c.label}
            </label>
            <textarea id="check-text" className="pub-input" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={c.placeholder} maxLength={4000} />
            <button type="submit" className="tab-btn" disabled={busy}>
              {busy ? c.searching : c.submit} <span className="arr" aria-hidden>→</span>
            </button>
          </form>
        </div>
        <div aria-live="polite">
          {hits && (
            <div className="mt-14">
              <h2 className="disp text-[clamp(28px,3vw,44px)]">{hits.length ? c.found(hits.length) : c.none}</h2>
              {hits.length ? (
                <div className="pub-grid mt-6">
                  {hits.map((v) => (
                    <VerdictFile key={v.id} v={v} />
                  ))}
                </div>
              ) : (
                <Link href={`/signaler?texte=${encodeURIComponent(text.slice(0, 600))}`} className="tab-btn mt-6">
                  {c.noneAction} <span className="arr" aria-hidden>→</span>
                </Link>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="frame-x bg-manila-deep py-[clamp(72px,9vw,130px)]" aria-labelledby="archive-title">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h2 id="archive-title" className="disp text-[clamp(40px,5vw,80px)] leading-[0.9]">
              {a.title}
            </h2>
            {page && <p className="typed mt-3 text-[15px] text-ink-soft">{a.count(page.total)}</p>}
          </div>
          <label className="block w-full max-w-sm">
            <span className="typed text-[15px] text-ink-soft">{a.filter}</span>
            <input type="search" className="pub-input mt-1" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
        {page && !page.items.length && <p className="mt-10 text-lg">{a.empty}</p>}
        <ul className="pub-list mt-10">
          {page?.items.map((v) => (
            <VerdictRow key={v.id} v={v} />
          ))}
        </ul>
        {page && page.total > page.items.length && (
          <button type="button" className="tab-btn mt-10" onClick={() => setLimit((l) => l + 9)}>
            {a.more}
          </button>
        )}
      </section>
    </>
  );
}
