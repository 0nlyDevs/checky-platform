"use client";

import type { components } from "@fanilo/shared";
import { useParams } from "next/navigation";
import { Fragment, useRef, useState } from "react";
import { IconArrowSquareOut, IconArrowUp, IconCircleNotch, IconFileText, IconImage, IconLink, IconPaperclip, IconRobot, IconTextT, IconWaveform, type Icon } from "@/lib/icons";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { postStream } from "@/lib/sse";
import { cn } from "@/lib/utils";

type Passage = Pick<components["schemas"]["Passage"], "n" | "title" | "url" | "text"> &
  Partial<Pick<components["schemas"]["Passage"], "kind" | "start_s" | "chunk_id">>;
type Step = { n: number; tool: string; input: Record<string, unknown>; summary: string };
type Exchange = { id: number; question: string; answer: string; passages: Passage[]; steps: Step[]; deep: boolean; state: "searching" | "answering" | "done" | "error"; error?: string; model?: string };

const KIND_ICON: Record<string, Icon> = { url: IconLink, pdf: IconFileText, image: IconImage, audio: IconWaveform, text: IconTextT };
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** Splits "… stable [1][2]." into text and citation chips; models also write 【1】. */
function Answer({ text, onCite }: { text: string; onCite: (n: number) => void }) {
  const parts = text.split(/(\[\d+\]|【\d+[^】]*】|\*\*[^*]+\*\*)/g);
  return (
    <p className="max-w-[70ch] whitespace-pre-line text-pretty">
      {parts.map((part, i) => {
        if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
        const m = /^(?:\[(\d+)\]|【(\d+)[^】]*】)$/.exec(part);
        if (!m) return <Fragment key={i}>{part}</Fragment>;
        const n = Number(m[1] ?? m[2]);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCite(n)}
            className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-border bg-card px-1 align-[0.1em] font-display text-xs font-semibold tabular hover:bg-accent"
            aria-label={`Passage ${n}`}
          >
            {n}
          </button>
        );
      })}
    </p>
  );
}

function PassageCard({ p, id, highlighted }: { p: Passage; id: string; highlighted: boolean }) {
  const Icon = (p.kind && KIND_ICON[p.kind]) || IconFileText;
  return (
    <li id={id} className={cn("scroll-mt-24 rounded-md border bg-card p-3.5 transition-colors duration-200", highlighted ? "border-ring ring-2 ring-ring/30" : "border-border")}>
      <p className="flex items-center gap-2 text-sm">
        <span className="font-display font-semibold tabular">[{p.n}]</span>
        <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        {p.url ? (
          <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 font-medium hover:underline">
            <span className="truncate">{p.title}</span>
            <IconArrowSquareOut className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          </a>
        ) : (
          <span className="truncate font-medium">{p.title}</span>
        )}
        {p.start_s != null && <span className="shrink-0 font-display tabular text-muted-foreground">{t.ask.at(clock(p.start_s))}</span>}
      </p>
      <p className="mt-1.5 line-clamp-4 text-sm text-pretty text-muted-foreground">{p.text}</p>
    </li>
  );
}

/** Numbers the answer actually cites, in order of first mention ([1] and 【1…】 alike). */
function cited(answer: string): Set<number> {
  return new Set([...answer.matchAll(/\[(\d+)\]|【(\d+)[^】]*】/g)].map((m) => Number(m[1] ?? m[2])));
}

/** What the answer rests on, first; what was read but not used, folded away. */
function Passages({ x, highlight }: { x: Exchange; highlight: string | null }) {
  const used = cited(x.answer);
  const main = x.state === "done" && used.size ? x.passages.filter((p) => used.has(p.n)) : x.passages;
  const rest = x.state === "done" && used.size ? x.passages.filter((p) => !used.has(p.n)) : [];
  const card = (p: Passage) => (
    <PassageCard key={p.chunk_id ?? `${x.id}-${p.n}`} p={p} id={`ex-${x.id}-p-${p.n}`} highlighted={highlight === `ex-${x.id}-p-${p.n}`} />
  );
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">{x.deep ? t.ask.readPages : t.ask.passages}</h3>
      <ol className="grid gap-2 sm:grid-cols-2">{main.map(card)}</ol>
      {rest.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">{t.ask.otherPassages(rest.length)}</summary>
          <ol className="mt-2 grid gap-2 sm:grid-cols-2">{rest.map(card)}</ol>
        </details>
      )}
    </div>
  );
}

/** Keep an answer: it becomes a text source on a claim, with its passages, so the check goes on there. */
function AttachToClaim({ ws, x }: { ws: string; x: Exchange }) {
  const [open, setOpen] = useState(false);
  const [itemId, setItemId] = useState<string>("");
  const [done, setDone] = useState(false);
  const { data } = useSWR<components["schemas"]["ItemPage"]>(open ? `/workspaces/${ws}/items?limit=100` : null, fetcher);

  async function attach() {
    if (!itemId) return;
    const used = cited(x.answer);
    const passages = x.passages
      .filter((p) => !used.size || used.has(p.n))
      .map((p) => `[${p.n}] ${p.title}${p.url ? ` (${p.url})` : ""}\n${p.text}`)
      .join("\n\n");
    try {
      await api(`/workspaces/${ws}/sources`, {
        method: "POST",
        body: JSON.stringify({ item_id: itemId, title: t.ask.attachTitle(x.question), text: `${x.answer}\n\n${passages}` }),
      });
      setDone(true);
      toast.success(t.ask.attached);
    } catch {
      toast.error(t.ask.errors.generic);
    }
  }

  if (done) return <p className="text-sm text-muted-foreground">{t.ask.attached}</p>;
  if (!open)
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <IconPaperclip aria-hidden />
        {t.ask.attach}
      </Button>
    );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Label htmlFor={`attach-${x.id}`} className="sr-only">
        {t.ask.attachPick}
      </Label>
      <Select value={itemId} onValueChange={setItemId}>
        <SelectTrigger id={`attach-${x.id}`} className="h-9 min-w-0 flex-1 basis-64 bg-card">
          <SelectValue placeholder={t.ask.attachPick} />
        </SelectTrigger>
        <SelectContent>
          {data?.items.map((i) => (
            <SelectItem key={i.id} value={i.id}>
              {((i.data as { ref?: string }).ref ? `${(i.data as { ref?: string }).ref} · ` : "") + i.title.slice(0, 80)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button size="sm" onClick={attach} disabled={!itemId}>
        {t.ask.attachConfirm}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
        {t.detail.cancel}
      </Button>
    </div>
  );
}

/** Ask every source of the newsroom; `embedded` drops the page frame (it lives in Vérifier). */
export function AskView({ embedded = false, initialQuestion = "" }: { embedded?: boolean; initialQuestion?: string }) {
  const { ws } = useParams<{ ws: string }>();
  const [question, setQuestion] = useState(initialQuestion);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [deep, setDeep] = useState(false);
  const counter = useRef(0);
  const busy = exchanges.some((e) => e.state === "searching" || e.state === "answering");

  function update(id: number, patch: (e: Exchange) => Partial<Exchange>) {
    setExchanges((list) => list.map((e) => (e.id === id ? { ...e, ...patch(e) } : e)));
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 2 || busy) return;
    const id = ++counter.current;
    setExchanges((list) => [{ id, question: q, answer: "", passages: [], steps: [], deep, state: "searching" }, ...list]);
    setQuestion("");
    try {
      const path = deep ? `/workspaces/${ws}/agent` : `/workspaces/${ws}/ask`;
      await postStream(path, deep ? { question: q } : { question: q, k: 4 }, (event, data) => {
        if (event === "citations") update(id, () => ({ passages: data as Passage[], state: "answering" }));
        else if (event === "step") update(id, (x) => ({ steps: [...x.steps, data as Step] }));
        else if (event === "answer") {
          const a = data as { text: string; citations: Passage[] };
          update(id, () => ({ answer: a.text, passages: a.citations, state: "answering" }));
        }
        else if (event === "delta") update(id, (x) => ({ answer: x.answer + (data as { text: string }).text }));
        else if (event === "done") update(id, () => ({ state: "done", model: (data as { model: string }).model }));
        else if (event === "error") {
          const code = (data as { code: string }).code;
          update(id, () => ({ state: "error", error: t.ask.errors[code] ?? t.ask.errors.generic }));
        }
      });
      update(id, (x) => (x.state === "answering" || x.state === "searching" ? { state: "done" } : {}));
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "generic";
      update(id, () => ({ state: "error", error: t.ask.errors[code] ?? t.ask.errors.generic }));
    }
  }

  function cite(exchange: number, n: number) {
    const target = `ex-${exchange}-p-${n}`;
    setHighlight(target);
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  return (
    <div className={embedded ? undefined : "mx-auto max-w-4xl px-4 pt-6 pb-12 lg:px-8 lg:pt-8"}>
      {embedded ? (
        <p className="mb-4 max-w-prose text-muted-foreground">{t.ask.lead}</p>
      ) : (
        <header className="pb-6">
          <h1 className="page-title">{t.ask.title}</h1>
          <p className="mt-1 max-w-prose text-muted-foreground">{t.ask.lead}</p>
        </header>
      )}

      <form onSubmit={ask} className="relative">
        <Label htmlFor="ask-question" className="sr-only">
          {t.ask.label}
        </Label>
        <textarea
          id="ask-question"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={t.ask.placeholder}
          className="w-full resize-none rounded-lg border border-input bg-card py-3 pr-14 pl-4 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
        />
        <div className="mt-2 flex items-start gap-2.5">
          <input
            id="ask-deep"
            type="checkbox"
            checked={deep}
            onChange={(e) => setDeep(e.target.checked)}
            className="mt-1 size-4 accent-primary"
          />
          <label htmlFor="ask-deep" className="text-sm">
            <span className="font-medium">{t.ask.deep}</span>
            <span className="block text-muted-foreground">{t.ask.deepHint}</span>
          </label>
        </div>
        <Button type="submit" size="icon" className="absolute top-[0.9rem] right-2.5 size-9" disabled={busy || question.trim().length < 2} aria-label={t.ask.submit}>
          {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconArrowUp aria-hidden />}
        </Button>
      </form>

      <div className="mt-8 space-y-10">
        {exchanges.map((x) => (
          <section key={x.id} className="space-y-4 border-t border-border pt-5" aria-live="polite">
            <h2 className="font-semibold text-pretty">{x.question}</h2>
            {x.state === "searching" && (
              <p className="flex items-center gap-2 text-muted-foreground" role="status">
                <IconCircleNotch className="size-4 animate-spin" aria-hidden />
                {t.ask.thinking}
              </p>
            )}
            {x.steps.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-muted-foreground">{t.ask.steps}</h3>
                <ol className="mt-1.5 space-y-1 border-l border-border pl-4 text-sm">
                  {x.steps.map((st) => (
                    <li key={st.n} className="flex flex-wrap items-baseline gap-x-2">
                      <IconRobot className="size-3.5 shrink-0 self-center text-muted-foreground" aria-hidden />
                      <span className="font-medium">{t.ask.stepTools[st.tool] ?? st.tool}</span>
                      <span className="min-w-0 truncate text-muted-foreground">
                        {String(Object.values(st.input)[0] ?? "")} → {st.summary}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {x.answer && <Answer text={x.answer} onCite={(n) => cite(x.id, n)} />}
            {x.state === "error" && (
              <p className="rounded-md bg-verdict-false-soft px-3 py-2 text-sm text-verdict-false-ink" role="alert">
                {x.error}
              </p>
            )}
            {x.state !== "searching" && x.passages.length === 0 && x.state !== "error" && (
              <p className="text-sm text-muted-foreground">{t.ask.noPassages}</p>
            )}
            {x.passages.length > 0 && <Passages x={x} highlight={highlight} />}
            {x.state === "done" && x.answer && <AttachToClaim ws={ws} x={x} />}
          </section>
        ))}
      </div>
    </div>
  );
}
