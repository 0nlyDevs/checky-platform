"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { fieldClass, Tag } from "@/components/registre/ui";
import { Button } from "@/components/ui/button";
import { api, ApiError, fetcher } from "@/lib/api";
import {
  IconArrowSquareOut,
  IconArrowsClockwise,
  IconCheckCircle,
  IconCircleNotch,
  IconPlus,
  IconQuestion,
  IconTimer,
  IconWarning,
  IconX,
  type Icon,
} from "@/lib/icons";
import { cn } from "@/lib/utils";
import { t } from "@/lib/i18n/live";

const registre = t.registre;

const f = registre.figures;

type Figure = {
  id: string;
  topic: string;
  label: string;
  value: string;
  unit: string | null;
  as_of: string | null;
  as_of_label: string;
  country: string | null;
  location: { name?: string };
  source_name: string;
  source_url: string | null;
  is_demo: boolean;
  shared: boolean;
  age_days: number | null;
  old: boolean;
};
type Verdict = "matches" | "differs" | "no_figure";
type NumberCheck = {
  claimed: string;
  kind: string;
  context: string;
  /** The part of the sentence the number belongs to. */
  clause?: string;
  verdict: Verdict;
  summary: string;
  figure: (Pick<Figure, "id" | "label" | "value" | "unit" | "as_of_label" | "source_name" | "source_url" | "old" | "is_demo" | "country">) | null;
};

// Comparing numbers is a fact computed by code: ink icons and words, never verdict colours.
const VERDICT_ICON: Record<Verdict, Icon> = { matches: IconCheckCircle, differs: IconWarning, no_figure: IconQuestion };

function SourceLink({ url, children }: { url: string | null; children: React.ReactNode }) {
  if (!url || !/^https?:\/\//i.test(url)) return <span>{children}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline underline-offset-4">
      {children}
      <IconArrowSquareOut className="size-3.5 shrink-0" aria-hidden />
    </a>
  );
}

/** Paste a text: each number with a unit set against the official figure on the same subject. */
function NumbersCheck({ ws }: { ws: string }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<NumberCheck[] | null>(null);
  async function run(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      setResult(await api<NumberCheck[]>(`/workspaces/${ws}/figures/check`, { method: "POST", body: JSON.stringify({ text }) }));
    } catch {
      toast.error(registre.page.failed);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-labelledby="numbers-title" className="mb-10">
      <h2 id="numbers-title" className="font-display text-xl font-bold">
        {f.check.title}
      </h2>
      <p className="mt-1 max-w-prose text-muted-foreground">{f.check.lead}</p>
      <form onSubmit={run} className="mt-3 rounded-md border border-input bg-card focus-within:border-foreground focus-within:ring-2 focus-within:ring-foreground/15">
        <label htmlFor="numbers-text" className="sr-only">
          {f.check.label}
        </label>
        <textarea
          id="numbers-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          maxLength={30000}
          placeholder={f.check.placeholder}
          className="block w-full resize-y rounded-t-md bg-transparent p-4 text-lg leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <div className="flex justify-end border-t border-border p-2">
          <Button type="submit" variant="action" size="xl" disabled={busy || !text.trim()}>
            {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
            {busy ? f.check.running : f.check.action}
          </Button>
        </div>
      </form>
      {result && (
        <div className="mt-4" aria-live="polite">
          {!result.length && <p className="text-muted-foreground">{f.check.none}</p>}
          <ul className="divide-y divide-border border-y border-foreground">
            {result.map((n, i) => {
              const Glyph = VERDICT_ICON[n.verdict];
              return (
                <li key={i} className="arrive grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" style={{ "--i": i } as React.CSSProperties}>
                  <div>
                    <p className="text-sm text-muted-foreground">{f.check.says}</p>
                    <p className="font-display text-2xl font-extrabold tabular-nums">{n.claimed}</p>
                    <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{n.clause || n.context}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">{f.check.official}</p>
                    {n.figure ? (
                      <>
                        <p className="font-display text-2xl font-extrabold tabular-nums">
                          {n.figure.value} {n.figure.unit}
                        </p>
                        <p className="mt-1 text-sm">
                          {n.figure.label} · <SourceLink url={n.figure.source_url}>{n.figure.source_name}</SourceLink>
                          {n.figure.as_of_label && ` · ${n.figure.as_of_label}`}
                        </p>
                        <div className="mt-1 flex gap-1.5">
                          {n.figure.old && (
                            <Tag>
                              <IconTimer className="size-3.5" aria-hidden />
                              {f.old}
                            </Tag>
                          )}
                          {n.figure.is_demo && <Tag strong>{f.demo}</Tag>}
                        </div>
                      </>
                    ) : (
                      <p className="text-sm">{n.summary}</p>
                    )}
                  </div>
                  <p className="inline-flex items-center gap-1.5 self-start font-display text-lg font-extrabold sm:justify-self-end">
                    <Glyph className="size-5 shrink-0" aria-hidden />
                    {f.check.verdict[n.verdict]}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

function FigureForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const value = (k: string) => String(form.get(k) || "").trim() || null;
    const body = {
      topic: value("topic"),
      label: value("label"),
      value: value("value"),
      unit: value("unit"),
      as_of: value("as_of"),
      country: value("country"),
      place: value("place"),
      source_name: value("source_name"),
      source_url: value("source_url"),
      keywords: (value("keywords") ?? "").split(",").map((k) => k.trim()).filter(Boolean),
    };
    try {
      await api(`/workspaces/${ws}/figures`, { method: "POST", body: JSON.stringify(body) });
      toast.success(f.form.saved);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError && e.status === 422 ? f.form.invalid : registre.page.failed);
    } finally {
      setBusy(false);
    }
  }
  const field = (name: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="block text-sm font-bold">
      {label}
      <input name={name} className={fieldClass} maxLength={300} {...props} />
    </label>
  );
  return (
    <form onSubmit={save} className="arrive mb-8 space-y-4 rounded-md border border-foreground bg-card p-5" aria-labelledby="figure-form">
      <div>
        <h2 id="figure-form" className="font-display text-xl font-bold">
          {f.form.title}
        </h2>
        <p className="mt-1 max-w-prose text-sm text-muted-foreground">{f.form.lead}</p>
      </div>
      {field("label", f.form.label, { required: true })}
      <div className="grid gap-4 sm:grid-cols-3">
        {field("value", f.form.value, { required: true, maxLength: 80, className: cn(fieldClass, "tabular-nums") })}
        {field("unit", f.form.unit, { maxLength: 40 })}
        {field("as_of", f.form.asOf, { required: true, pattern: "\\d{4}(-\\d{2}){0,2}", maxLength: 10, placeholder: "2025" })}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {field("topic", f.form.topic, { required: true, maxLength: 80 })}
        {field("country", f.form.country, { maxLength: 80, defaultValue: "Madagascar" })}
        {field("place", f.form.place, { maxLength: 200 })}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {field("source_name", f.form.sourceName, { required: true, maxLength: 200 })}
        {field("source_url", f.form.sourceUrl, { required: true, type: "url", maxLength: 2000 })}
      </div>
      {field("keywords", f.form.keywords, { maxLength: 600 })}
      {error && (
        <p role="alert" className="text-sm font-bold text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={busy}>
        {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
        {busy ? f.form.saving : f.form.save}
      </Button>
    </form>
  );
}

export function FiguresView() {
  const { ws } = useParams<{ ws: string }>();
  const { data, error, mutate } = useSWR<Figure[]>(`/workspaces/${ws}/figures`, fetcher);
  const [topic, setTopic] = useState("");
  const [country, setCountry] = useState("");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const topics = useMemo(() => [...new Set((data ?? []).map((x) => x.topic))].sort((a, b) => a.localeCompare(b, "fr")), [data]);
  const countries = useMemo(
    () => [...new Set((data ?? []).map((x) => x.country).filter((c): c is string => !!c))].sort((a, b) => a.localeCompare(b, "fr")),
    [data],
  );
  const needle = q.trim().toLocaleLowerCase("fr");
  const shown = (data ?? []).filter(
    (x) =>
      (!topic || x.topic === topic) &&
      (!country || x.country === country) &&
      (!needle || `${x.label} ${x.topic} ${x.source_name} ${x.country ?? ""}`.toLocaleLowerCase("fr").includes(needle)),
  );
  const grouped = topics.map((name) => [name, shown.filter((x) => x.topic === name)] as const).filter(([, rows]) => rows.length);

  async function refresh() {
    setRefreshing(true);
    try {
      await api(`/workspaces/${ws}/figures/refresh`, { method: "POST" });
      toast.success(f.refreshed);
      setTimeout(() => void mutate(), 4000);
      void mutate();
    } catch {
      toast.error(registre.page.failed);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 *:max-w-5xl lg:px-8 lg:pt-8">
      <header className="flex flex-wrap items-start justify-between gap-4 pb-6">
        <div className="min-w-0">
          <h1 className="page-title">{f.title}</h1>
          {data && <p className="mt-1 text-sm text-muted-foreground">{f.count(data.length)}</p>}
          <p className="mt-3 max-w-prose text-muted-foreground">{f.lead}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(
            <Button variant="outline" size="lg" onClick={refresh} disabled={refreshing}>
              <IconArrowsClockwise className={cn(refreshing && "animate-spin")} aria-hidden />
              {f.refresh}
            </Button>
          )}
          <Button size="lg" onClick={() => setAdding(!adding)} aria-expanded={adding}>
            {adding ? <IconX aria-hidden /> : <IconPlus aria-hidden />}
            {adding ? f.close : f.add}
          </Button>
        </div>
      </header>
      {adding && (
        <FigureForm
          ws={ws}
          onDone={() => {
            setAdding(false);
            void mutate();
          }}
        />
      )}
      <NumbersCheck ws={ws} />

      <div className="flex flex-wrap items-end gap-3 border-b border-foreground pb-4">
        <div role="group" aria-label={f.topicsLabel} className="flex min-w-0 flex-1 flex-wrap gap-1">
          {["", ...topics].map((name) => (
            <button
              key={name || "all"}
              type="button"
              aria-pressed={topic === name}
              onClick={() => setTopic(name)}
              className={cn(
                "h-10 rounded-md px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                topic === name ? "bg-foreground font-bold text-background" : "hover:bg-accent",
              )}
            >
              {name || f.allTopics}
            </button>
          ))}
        </div>
        <label className="block text-sm font-bold">
          {f.country}
          <select
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="mt-1 block h-10 rounded-md border border-input bg-card px-2 font-normal outline-none focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
          >
            <option value="">{f.allCountries}</option>
            {countries.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="block w-full text-sm font-bold sm:w-56">
          {f.search}
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 font-normal outline-none focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
          />
        </label>
      </div>

      {error && (
        <div role="alert" className="py-6">
          <p>{f.loadFailed}</p>
          <Button variant="outline" className="mt-2" onClick={() => void mutate()}>
            {f.retry}
          </Button>
        </div>
      )}
      {data && !shown.length && <p className="py-8 text-muted-foreground">{f.empty}</p>}
      {grouped.map(([name, rows]) => (
        <section key={name} className="mt-8" aria-labelledby={`topic-${name}`}>
          <h2 id={`topic-${name}`} className="font-display text-lg font-bold first-letter:uppercase">
            {name}
          </h2>
          <ul className="mt-2 divide-y divide-border border-t border-border">
            {rows.map((x) => (
              <li key={x.id} className="grid gap-x-6 gap-y-1 py-4 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div className="min-w-0">
                  <p className="font-bold text-pretty">{x.label}</p>
                  <p className="text-sm text-muted-foreground">
                    {[x.country, x.location?.name && x.location.name !== x.country ? x.location.name : null, x.as_of_label && f.asOf(x.as_of_label)]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <p className="mt-1 text-sm">
                    <SourceLink url={x.source_url}>{x.source_name}</SourceLink>
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {x.old && (
                      <Tag>
                        <IconTimer className="size-3.5" aria-hidden />
                        <span title={f.oldHelp}>{f.old}</span>
                      </Tag>
                    )}
                    {x.is_demo && <Tag strong>{f.demo}</Tag>}
                    {x.shared && <Tag>{f.shared}</Tag>}
                  </div>
                </div>
                <p className="font-display text-2xl font-extrabold tabular-nums sm:text-right">
                  {x.value}
                  {x.unit && <span className="ml-1 text-base font-bold">{x.unit}</span>}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
