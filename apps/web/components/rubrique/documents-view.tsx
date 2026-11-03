"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useDeferredValue, useState } from "react";
import useSWR from "swr";
import { IconArrowSquareOut, IconFileText, IconMagnifyingGlass } from "@/lib/icons";
import { AskView } from "@/components/ask/ask-view";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { DemoTag, LoadFailed, Section } from "./bits";
import type { DocumentRow, Prefs } from "./types";
import { useStickyColumns } from "@/hooks/use-sticky-columns";

const d = t.rubrique.documents;
const ALL = "__all";
const dateFmt = dateFormat({ day: "numeric", month: "long", year: "numeric" });

function day(iso: string) {
  const v = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return Number.isNaN(v.getTime()) ? iso : dateFmt.format(v);
}

function DocRow({ ws, doc, i }: { ws: string; doc: DocumentRow; i: number }) {
  const type = d.types[doc.doc_type] ?? doc.doc_type;
  return (
    <li className="arrive border-b border-border py-4" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="inline-flex items-center gap-1.5 font-display font-bold">
          <IconFileText className="size-4" aria-hidden />
          {type}
        </span>
        {doc.issuer && <span className="font-bold">{doc.issuer}</span>}
        <span className="text-muted-foreground">{doc.published_at ? d.published(day(doc.published_at)) : d.added(day(doc.created_at))}</span>
        {doc.demo && <DemoTag />}
      </p>
      <p className="mt-1 font-bold text-pretty md:text-[1.05rem]">{doc.title}</p>
      {doc.excerpt && <p className="mt-1 line-clamp-2 text-sm text-pretty text-muted-foreground">{doc.excerpt}</p>}
      <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {doc.beats.length > 0 && <span className="text-muted-foreground">{doc.beats.join(", ")}</span>}
        {doc.url && (
          <a href={doc.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold underline underline-offset-4">
            {d.open}
            <IconArrowSquareOut className="size-3.5" aria-hidden />
          </a>
        )}
        {doc.item_id && (
          <Link href={`/w/${ws}/claims/${doc.item_id}` as never} className="font-bold underline underline-offset-4">
            {t.rubrique.circulating.open}
          </Link>
        )}
      </p>
    </li>
  );
}

/**
 * Documents: the communiqués, decrees, reports and notes among the newsroom's sources, newest
 * first, filtered by beat or words, with « Interroger les documents » (the sources RAG) beside them.
 */
export function DocumentsView() {
  const columns = useStickyColumns<HTMLDivElement>();
  const { ws } = useParams<{ ws: string }>();
  const [q, setQ] = useState("");
  const [topic, setTopic] = useState(ALL);
  const query = useDeferredValue(q.trim());
  const params = new URLSearchParams();
  if (topic !== ALL) params.set("topic", topic);
  if (query) params.set("q", query);
  const suffix = params.toString() ? `?${params}` : "";
  const docs = useSWR<DocumentRow[]>(`/workspaces/${ws}/documents${suffix}`, fetcher, { keepPreviousData: true });
  const prefs = useSWR<Prefs>(`/workspaces/${ws}/me/prefs`, fetcher);

  return (
    <div className="@container mx-auto max-w-[90rem] px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">{d.title}</h1>
          <p className="mt-2 max-w-prose text-pretty text-muted-foreground">{d.lead}</p>
        </div>
        <Link href={`/w/${ws}/sources` as never} className="text-sm font-bold underline underline-offset-4">
          {d.sources}
        </Link>
      </header>

      <div ref={columns} className="mt-6 grid gap-x-10 gap-y-10 @5xl:grid-cols-[minmax(0,1fr)_28rem]">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2">
            <div className="relative min-w-0 flex-1 basis-56">
              <IconMagnifyingGlass className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={d.search} aria-label={d.search} className="h-10 bg-card pl-9" />
            </div>
            <Select value={topic} onValueChange={setTopic}>
              <SelectTrigger size="sm" aria-label={d.topic} className="w-auto min-w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{d.allTopics}</SelectItem>
                {(prefs.data?.beats_offered ?? []).map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="mt-4">
            {docs.error ? (
              <LoadFailed onRetry={() => void docs.mutate()} />
            ) : !docs.data ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))}
              </div>
            ) : docs.data.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-4 py-6">
                <p className="font-bold">{d.empty}</p>
                <p className="mt-1 text-sm text-muted-foreground">{d.emptyHint}</p>
              </div>
            ) : (
              <ul className="border-t border-foreground">
                {docs.data.map((doc, i) => (
                  <DocRow key={doc.id} ws={ws} doc={doc} i={i} />
                ))}
              </ul>
            )}
          </div>
        </div>

        <Section id="interroger" title={d.ask} lead={d.askLead} className="min-w-0 self-start">
          <AskView embedded />
        </Section>
      </div>
    </div>
  );
}
