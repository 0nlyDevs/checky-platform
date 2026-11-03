"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Em, Lines, PillChoice } from "@/components/site/public/kit";
import { IconArrowSquareOut, IconCopy, IconMagnifyingGlass, IconSealCheck, IconWarning } from "@/lib/icons";
import { publicApi } from "@/lib/public-api";
import { RegistryDiff } from "./registry-diff";
import { communiqueRef, frenchDay, type OfficialEntry } from "./types";
import { Tag } from "./ui";
import { t } from "@/lib/i18n/live";

const registre = t.registre;

const f = registre.feed;
type Kind = "all" | "original" | "fake_caught";

function Entry({ e, index }: { e: OfficialEntry; index: number }) {
  async function copy() {
    await navigator.clipboard.writeText(`${window.location.origin}/officiel#c-${e.id}`);
    toast.success(f.copied);
  }
  const fake = e.kind === "fake_caught";
  return (
    <li id={`c-${e.id}`} className="arrive scroll-mt-28 rounded-[24px] border border-border bg-card p-6 md:p-7" style={{ "--i": Math.min(index, 8) } as React.CSSProperties}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="font-display font-bold">{fake ? f.fake : f.original}</span>
        <span className="text-muted-foreground">
          {fake
            ? registre.entry.caught(frenchDay(e.created_at))
            : [e.number && registre.entry.number(e.number), e.issuer, e.issued_on && registre.entry.issued(frenchDay(e.issued_on))]
                .filter(Boolean)
                .join(" · ")}
        </span>
      </p>
      {/* A fake borrows its original's number and title: the heading says which one it imitates. */}
      <h2 className="mt-1 font-display text-xl leading-snug font-bold text-pretty">
        {fake ? registre.entry.imitates(communiqueRef(e.original ?? e)) : e.title}
      </h2>
      {fake && <p className="mt-1 text-muted-foreground">{t.common.quote((e.original ?? e).title)}</p>}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {e.is_demo && <Tag strong>{registre.entry.demo}</Tag>}
        {e.sealed && (
          <Tag strong>
            <IconSealCheck className="size-3.5" aria-hidden />
            {registre.entry.sealed}
          </Tag>
        )}
        {!fake && e.confirmed && <Tag>{registre.entry.confirmed}</Tag>}
        {!fake && e.fakes > 0 && <Tag>{registre.entry.fakes(e.fakes)}</Tag>}
        <Tag>{f.by(e.newsroom.name)}</Tag>
      </div>
      {fake ? (
        <div className="mt-3">
          <RegistryDiff diff={e.diff} summary={e.summary} changedNumbers={e.changed_numbers} />
        </div>
      ) : (
        <details className="mt-3">
          <summary className="cursor-pointer font-bold underline-offset-4 hover:underline">{f.more}</summary>
          <p className="mt-3 max-w-prose rounded-[16px] bg-raised p-4 whitespace-pre-wrap">{e.text}</p>
          {e.url && /^https?:\/\//i.test(e.url) && (
            <a href={e.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm font-bold underline underline-offset-4">
              {registre.entry.source}
              <IconArrowSquareOut className="size-4" aria-hidden />
            </a>
          )}
        </details>
      )}
      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        {e.seal_url && (
          <a href={e.seal_url} className="inline-flex items-center gap-1 font-bold underline underline-offset-4">
            <IconSealCheck className="size-4" aria-hidden />
            {f.checkSeal}
          </a>
        )}
        <button type="button" onClick={copy} className="inline-flex items-center gap-1 underline-offset-4 hover:underline">
          <IconCopy className="size-4" aria-hidden />
          {f.copy}
        </button>
      </div>
    </li>
  );
}

/** /officiel: what the institutions published and the fakes caught imitating it, newest first. */
export function OfficialFeed() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<Kind>("all");
  const [limit, setLimit] = useState(30);
  const [page, setPage] = useState<{ items: OfficialEntry[]; total: number } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (q.trim()) params.set("q", q.trim());
      if (kind !== "all") params.set("kind", kind);
      publicApi<{ items: OfficialEntry[]; total: number }>(`/registry?${params}`)
        .then((p) => {
          setPage(p);
          setFailed(false);
        })
        .catch(() => setFailed(true));
    }, 250);
    return () => clearTimeout(id);
  }, [q, kind, limit]);

  // A shared link (#c-<id>) lands on its entry once the list is there.
  useEffect(() => {
    const target = page && window.location.hash ? document.getElementById(window.location.hash.slice(1)) : null;
    target?.scrollIntoView();
  }, [page]);

  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-10 pb-24 lg:px-10 lg:pt-16">
      <Lines className="pub-display" lines={t.look.official.hero.map((line, i) => <Em key={i} text={line} />)} />
      <p className="pub-lead rise mt-7 max-w-[62ch]" style={{ "--d": "0.25s" } as React.CSSProperties}>
        {f.lead}
      </p>
      <div className="rise mt-10 flex flex-wrap items-center justify-between gap-4" style={{ "--d": "0.35s" } as React.CSSProperties}>
        <PillChoice
          value={kind}
          onChange={setKind}
          label={f.tabsLabel}
          options={[
            { value: "all", label: f.tabs.all },
            { value: "original", label: f.tabs.original, icon: IconSealCheck },
            { value: "fake_caught", label: f.tabs.fake_caught, icon: IconWarning },
          ]}
        />
        <label className="pub-search pub-search-wide">
          <span className="sr-only">{f.filter}</span>
          <IconMagnifyingGlass className="size-5 shrink-0 text-muted-foreground" aria-hidden />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={f.filter} />
        </label>
      </div>
      {page && <p className="mt-6 text-muted-foreground">{f.count(page.total)}</p>}
      {failed && (
        <p role="alert" className="py-8">
          {f.failed}
        </p>
      )}
      {page && !page.items.length && <p className="py-8 text-muted-foreground">{f.empty}</p>}
      <ul className="mt-4 flex max-w-4xl flex-col gap-4">
        {page?.items.map((e, i) => (
          <Entry key={e.id} e={e} index={i} />
        ))}
      </ul>
      {page && page.total > page.items.length && (
        <button type="button" onClick={() => setLimit(limit + 30)} className="pub-ghost-btn mt-8">
          {f.loadMore}
        </button>
      )}
    </div>
  );
}
