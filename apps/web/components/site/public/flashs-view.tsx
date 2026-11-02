"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useDay, useLang, useT } from "@/lib/i18n";
import { IconBroadcast, IconCheck, IconCopy, IconPrinter } from "@/lib/icons";
import { publicApi } from "@/lib/public-api";
import { cn } from "@/lib/utils";

type Line = { n: number; id: string; ref: string | null; verdict: string; title: string; newsroom: string; link: string; fr: string; mg: string };
type Flashs = { date: string; newsroom: { slug: string; name: string } | null; items: Line[] };
type Radio = { name: string; frequency: string | null; languages: string[]; newsroom: { slug: string; name: string } };
type Voice = "fr" | "mg";

/**
 * « Flashs du jour »: the verdicts signed today as numbered lines a presenter reads on air, a
 * newsroom copies into WhatsApp or prints for a notice board. Text only, light enough for a slow
 * connection. A partner radio opens it with `?radio=<token>` and marks each flash « Diffusé ».
 */
export function FlashsView() {
  const t = useT();
  const l = t.publicLayer.flashs;
  const day = useDay();
  const lang = useLang();
  const token = useSearchParams().get("radio");
  const [radio, setRadio] = useState<Radio | null | "bad">(null);
  const [data, setData] = useState<Flashs | null | "failed">(null);
  const [chosen, setChosen] = useState<Voice | null>(null);
  const [copied, setCopied] = useState(false);
  const [aired, setAired] = useState<Record<string, "busy" | "done" | "failed">>({});
  const voice: Voice = chosen ?? (lang === "mg" ? "mg" : "fr");

  useEffect(() => {
    let live = true;
    (async () => {
      let room: string | null = null;
      if (token) {
        try {
          const r = await publicApi<Radio>(`/radios/${encodeURIComponent(token)}`);
          if (live) setRadio(r);
          room = r.newsroom.slug;
        } catch {
          if (live) setRadio("bad");
        }
      }
      try {
        const res = await publicApi<Flashs>(`/flashs${room ? `?newsroom=${encodeURIComponent(room)}` : ""}`);
        if (live) setData(res);
      } catch {
        if (live) setData("failed");
      }
    })();
    return () => {
      live = false;
    };
  }, [token]);

  const lines = data && data !== "failed" ? data.items : [];
  const text = lines.map((x) => x[voice]).join("\n\n");

  async function markAired(id: string) {
    if (!token) return;
    setAired((a) => ({ ...a, [id]: "busy" }));
    try {
      await publicApi(`/radios/${encodeURIComponent(token)}/diffuse`, { method: "POST", body: JSON.stringify({ item_id: id }) });
      setAired((a) => ({ ...a, [id]: "done" }));
    } catch {
      setAired((a) => ({ ...a, [id]: "failed" }));
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-20 print:max-w-none print:p-0">
      <h1 className="page-title">{l.title}</h1>
      {radio && radio !== "bad" && (
        <p className="mt-2 font-bold">
          {l.radio([radio.name, radio.frequency].filter(Boolean).join(" "))} · {radio.newsroom.name}
        </p>
      )}
      <p className="mt-3 max-w-[60ch] text-lg text-pretty text-muted-foreground print:hidden">{radio && radio !== "bad" ? l.radioLead : l.lead}</p>
      {radio === "bad" && (
        <p className="mt-3 font-bold" role="alert">
          {l.badRadio}
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3 print:hidden">
        <div role="group" aria-label={l.language} className="flex rounded-md border border-border bg-card p-0.5">
          {(["fr", "mg"] as const).map((v) => (
            <button
              key={v}
              type="button"
              lang={v}
              aria-pressed={voice === v}
              onClick={() => setChosen(v)}
              className={cn(
                "h-9 min-w-11 rounded-sm px-3 font-display text-sm font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring",
                voice === v ? "bg-foreground text-background" : "hover:bg-accent",
              )}
            >
              {t.publicLayer.lang.short[v]}
            </button>
          ))}
        </div>
        <Button variant="action" size="lg" disabled={!lines.length} onClick={() => navigator.clipboard?.writeText(text).then(() => setCopied(true))}>
          {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
          {copied ? l.copied : l.copy}
        </Button>
        <Button variant="outline" size="lg" disabled={!lines.length} onClick={() => window.print()}>
          <IconPrinter aria-hidden />
          {l.print}
        </Button>
      </div>
      {voice === "mg" && <p className="mt-2 text-sm text-muted-foreground print:hidden">{l.mgNote}</p>}

      <section className="mt-8" aria-live="polite">
        {data === "failed" ? (
          <p className="text-lg" role="alert">
            {l.failed}
          </p>
        ) : !data ? (
          <div className="h-40 animate-pulse rounded-md bg-muted" />
        ) : (
          <>
            <h2 className="font-display text-lg font-bold">
              {l.date(day(data.date))}
              {data.newsroom && ` · ${data.newsroom.name}`}
            </h2>
            {!lines.length ? (
              <p className="mt-4 text-lg">{l.empty}</p>
            ) : (
              <ol className="mt-3 border-t border-foreground">
                {lines.map((x) => {
                  const state = aired[x.id];
                  return (
                    <li key={x.id} className="border-b border-border py-4 break-inside-avoid">
                      <p lang={voice} className="max-w-[70ch] text-lg leading-relaxed text-pretty">
                        {x[voice]}
                      </p>
                      {token && radio && radio !== "bad" && (
                        <div className="mt-2 flex flex-wrap items-center gap-3 print:hidden">
                          <Button variant="outline" size="lg" disabled={state === "busy" || state === "done"} onClick={() => markAired(x.id)} aria-pressed={state === "done"}>
                            {state === "done" ? <IconCheck aria-hidden /> : <IconBroadcast aria-hidden />}
                            {state === "done" ? l.aired : l.markAired}
                          </Button>
                          {state === "failed" && (
                            <span className="text-sm font-bold" role="alert">
                              {l.airFailed}
                            </span>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </>
        )}
      </section>
    </div>
  );
}
