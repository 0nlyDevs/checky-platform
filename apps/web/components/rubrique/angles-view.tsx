"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconCircleNotch, IconSparkle } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";
import { Section } from "./bits";
import type { Angle, AnglesOut, Fact, Prefs } from "./types";

const g = t.rubrique.angles;

/** The dossier an angle can be kept in: the one asked about, else the first dossier it rests on. */
function keepTarget(angle: Angle, itemId?: string): { id: string; ref: string | null } | null {
  if (itemId) return { id: itemId, ref: null };
  const fact = angle.rests_on.find((f) => f.item_id && (f.kind === "claim" || f.kind === "missing" || f.kind === "verdict"));
  if (!fact?.item_id) return null;
  return { id: fact.item_id, ref: fact.label.match(/[A-Z]{2,5}-\d{3,}/)?.[0] ?? null };
}

function FactLine({ ws, fact }: { ws: string; fact: Fact }) {
  const kind = g.factKinds[fact.kind] ?? fact.kind;
  // Labels often open with their kind already (« Dossier FAN-0141 … », « Chiffre disponible … »).
  const said = fact.label.toLowerCase().startsWith(kind.toLowerCase().slice(0, 6));
  return (
    <>
      <span className="font-display font-bold tabular">[{fact.n}]</span> {!said && <span className="font-bold">{kind} · </span>}
      {fact.item_id ? (
        <Link href={`/w/${ws}/claims/${fact.item_id}` as never} className="text-pretty underline-offset-2 hover:underline">
          {fact.label}
        </Link>
      ) : (
        <span className="text-pretty">{fact.label}</span>
      )}
    </>
  );
}

function AngleItem({ ws, angle, model, itemId, i }: { ws: string; angle: Angle; model: string | null; itemId?: string; i: number }) {
  const [kept, setKept] = useState(false);
  const [busy, setBusy] = useState(false);
  const target = keepTarget(angle, itemId);

  async function keep() {
    if (!target) return;
    setBusy(true);
    try {
      await api(`/workspaces/${ws}/items/${target.id}/angles/keep`, { method: "POST", body: JSON.stringify({ angle }) });
      setKept(true);
      toast(g.kept);
    } catch {
      toast.error(g.keepFailed);
    } finally {
      setBusy(false);
    }
  }

  // An AI suggestion: dashed until a journalist keeps it.
  return (
    <li className={cn("arrive flex flex-col rounded-md bg-card p-4", kept ? "border-2 border-foreground" : "border-2 border-dashed border-foreground")} style={{ "--i": i } as React.CSSProperties}>
      <p className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
        <IconSparkle className="size-4" aria-hidden />
        {kept ? g.kept : g.suggestion}
        {model && !kept && <span>· {g.model(model)}</span>}
      </p>
      <h3 className="mt-1.5 font-display text-lg leading-snug font-bold text-pretty">{angle.title}</h3>
      {angle.why && <p className="mt-1 text-sm text-pretty">{angle.why}</p>}
      <p className="mt-3 text-sm font-bold">{g.restsOn}</p>
      <ul className="mt-1 space-y-1 text-sm">
        {angle.rests_on.map((f) => (
          <li key={f.n}>
            <FactLine ws={ws} fact={f} />
          </li>
        ))}
      </ul>
      {angle.missing_figure && (
        <p className="mt-3 text-sm">
          <span className="font-bold">{g.missing} : </span>
          {angle.missing_figure}
        </p>
      )}
      {target && !kept && (
        <div className="mt-auto pt-4">
          <Button variant="outline" size="lg" onClick={keep} disabled={busy}>
            {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
            {target.ref ? g.keepFor(target.ref) : g.keep}
          </Button>
        </div>
      )}
    </li>
  );
}

/**
 * Angles: the facts the newsroom already holds on a subject (numbered), then the angles the model
 * suggests on them. An angle that cites no fact, or a figure absent from them, is dropped by the
 * API. `itemId` grounds them on one dossier and keeps them there; `primary` makes « Suggérer » the
 * screen's one primary button (the Angles page); inside another screen it stays secondary.
 */
export function AnglesPanel({ ws, itemId, initialTopic = "", primary = false }: { ws: string; itemId?: string; initialTopic?: string; primary?: boolean }) {
  const [topic, setTopic] = useState(initialTopic);
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<AnglesOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prefs = useSWR<Prefs>(itemId ? null : `/workspaces/${ws}/me/prefs`, fetcher);

  async function run(subject: string) {
    if (!subject.trim() && !itemId) return;
    setBusy(true);
    setError(null);
    try {
      setOut(await api<AnglesOut>(`/workspaces/${ws}/angles`, { method: "POST", body: JSON.stringify({ topic: subject.trim() || null, item_id: itemId ?? null }) }));
    } catch (err) {
      setOut(null);
      setError(err instanceof ApiError && err.code === "ai_disabled" ? g.disabled : err instanceof ApiError && err.status === 503 ? g.unavailable : g.failed);
    } finally {
      setBusy(false);
    }
  }

  const beats = prefs.data?.beats.length ? prefs.data.beats : (prefs.data?.beats_offered ?? []).slice(0, 6);

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(topic);
        }}
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
      >
        <label className="min-w-0 flex-1">
          <span className="font-bold">{g.topic}</span>
          <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder={g.topicPlaceholder} maxLength={200} className="mt-1.5 h-12 bg-card text-base" />
        </label>
        <Button type="submit" variant={primary ? "action" : "outline"} size="xl" disabled={busy || (!topic.trim() && !itemId)}>
          {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconSparkle aria-hidden />}
          {busy ? g.working : g.suggest}
        </Button>
      </form>
      {!itemId && beats.length > 0 && (
        <p className="mt-3 flex flex-wrap items-center gap-1.5 text-sm">
          <span className="mr-1 text-muted-foreground">{g.quick}</span>
          {beats.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => {
                setTopic(b);
                void run(b);
              }}
              disabled={busy}
              className="inline-flex h-9 items-center rounded-md border border-input bg-card px-3 outline-none hover:border-foreground focus-visible:ring-2 focus-visible:ring-ring"
            >
              {b}
            </button>
          ))}
        </p>
      )}

      {error && (
        <p role="alert" className="mt-5 rounded-md border border-border bg-card p-4 font-bold">
          {error}
        </p>
      )}

      {out && (
        <div className="mt-8 grid gap-x-10 gap-y-8 @4xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-w-0">
            {out.facts.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-5 font-bold">{g.noFacts}</p>
            ) : (
              <>
                <ul className="grid gap-4 @3xl:grid-cols-2">
                  {out.angles.map((a, i) => (
                    <AngleItem key={a.title} ws={ws} angle={a} model={out.model} itemId={itemId} i={i} />
                  ))}
                </ul>
                {out.dropped > 0 && <p className="mt-3 text-sm text-muted-foreground">{g.dropped(out.dropped)}</p>}
              </>
            )}
          </div>
          {out.facts.length > 0 && (
            <Section id="faits" title={g.facts} lead={g.factsLead}>
              <ol className="space-y-2 text-sm">
                {out.facts.map((f) => (
                  <li key={f.n}>
                    <FactLine ws={ws} fact={f} />
                  </li>
                ))}
              </ol>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

/** The Angles page: a subject (from `?sujet=`, or one of my beats) or a dossier (`?dossier=`). */
export function AnglesView() {
  const { ws } = useParams<{ ws: string }>();
  const params = useSearchParams();
  const itemId = params.get("dossier") ?? undefined;
  return (
    <div className="@container mx-auto max-w-[90rem] px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <h1 className="page-title">{g.title}</h1>
      <p className="mt-2 max-w-prose text-pretty text-muted-foreground">{g.lead}</p>
      <div className="mt-6">
        <AnglesPanel ws={ws} itemId={itemId} initialTopic={params.get("sujet") ?? ""} primary />
      </div>
    </div>
  );
}
