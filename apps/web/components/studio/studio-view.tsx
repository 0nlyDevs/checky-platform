"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DemoTag, LoadFailed, Section } from "@/components/rubrique/bits";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconCircleNotch, IconMicrophone, IconPlus } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { ShowBrief, Speaker } from "./types";

const s = t.studio;

function StatusDot({ status }: { status: ShowBrief["status"] }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-bold">
      <span
        className={cn(
          "size-2 rounded-full border border-foreground",
          status === "live" ? "bg-foreground" : "bg-transparent",
        )}
        aria-hidden
      />
      {s.list.status[status] ?? status}
    </span>
  );
}

function NewShow({ ws, onCreated }: { ws: string; onCreated: (id: string) => void }) {
  const f = s.form;
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [station, setStation] = useState("");
  const [topics, setTopics] = useState("");
  const [language, setLanguage] = useState<"fr" | "mg">("fr");
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [busy, setBusy] = useState(false);
  const { data: newsroom } = useSWR<{ settings?: { beats?: string[] } }>(`/workspaces/${ws}`, fetcher);
  const beats = newsroom?.settings?.beats ?? [];
  const [chosen, setChosen] = useState<string[]>([]);

  const toggleTopic = (b: string) =>
    setChosen((c) => (c.includes(b) ? c.filter((x) => x !== b) : [...c, b]));

  async function create() {
    setBusy(true);
    try {
      const show = await api<ShowBrief>(`/workspaces/${ws}/studio`, {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          station: station.trim() || null,
          topics: [...chosen, ...topics.split(",").map((x) => x.trim()).filter(Boolean)].slice(0, 12),
          language,
          input: "microphone",
          speakers,
        }),
      });
      onCreated(show.id);
    } catch {
      toast(f.failed);
      setBusy(false);
    }
  }

  if (!open)
    return (
      <Button variant="action" onClick={() => setOpen(true)} className="gap-1.5">
        <IconPlus className="size-4" aria-hidden /> {s.list.newShow}
      </Button>
    );

  return (
    <Section title={f.title} id="new-show" className="mt-4">
      <div className="grid gap-4">
        <label className="grid gap-1">
          <span className="text-sm font-bold">{f.name}</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={f.namePlaceholder}
            className="h-10 rounded-md border border-border bg-background px-3"
          />
        </label>
        <label className="grid gap-1">
          <span className="text-sm font-bold">{f.station}</span>
          <input
            value={station}
            onChange={(e) => setStation(e.target.value)}
            placeholder={f.stationPlaceholder}
            className="h-10 rounded-md border border-border bg-background px-3"
          />
        </label>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-bold">{f.topics}</legend>
          <p className="text-sm text-muted-foreground">{f.topicsLead}</p>
          <div className="flex flex-wrap gap-1.5">
            {beats.map((b) => (
              <button
                key={b}
                type="button"
                aria-pressed={chosen.includes(b)}
                onClick={() => toggleTopic(b)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm",
                  chosen.includes(b)
                    ? "border-foreground bg-foreground text-background"
                    : "border-border hover:border-foreground",
                )}
              >
                {b}
              </button>
            ))}
          </div>
          <input
            value={topics}
            onChange={(e) => setTopics(e.target.value)}
            aria-label={f.topics}
            placeholder={beats.slice(0, 2).join(", ")}
            className="h-10 rounded-md border border-border bg-background px-3"
          />
        </fieldset>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-bold">{f.language}</legend>
          <div className="flex gap-2">
            {(["fr", "mg"] as const).map((l) => (
              <button
                key={l}
                type="button"
                aria-pressed={language === l}
                onClick={() => setLanguage(l)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm",
                  language === l ? "border-foreground bg-foreground text-background" : "border-border",
                )}
              >
                {f.languages[l]}
              </button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">{language === "mg" ? f.mgNote : f.frNote}</p>
        </fieldset>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-bold">{f.debate}</legend>
          <p className="text-sm text-muted-foreground">{f.debateLead}</p>
          {speakers.map((sp, i) => (
            <div key={sp.id} className="flex flex-wrap items-end gap-2">
              <label className="grid flex-1 gap-1">
                <span className="text-sm">{f.speakerName(i + 1)}</span>
                <input
                  value={sp.name}
                  onChange={(e) =>
                    setSpeakers((all) => all.map((x) => (x.id === sp.id ? { ...x, name: e.target.value } : x)))
                  }
                  placeholder={f.speakerPlaceholder}
                  className="h-10 rounded-md border border-border bg-background px-3"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-sm">{f.camp}</span>
                <input
                  value={sp.camp ?? ""}
                  onChange={(e) =>
                    setSpeakers((all) => all.map((x) => (x.id === sp.id ? { ...x, camp: e.target.value || null } : x)))
                  }
                  placeholder={f.noCamp}
                  className="h-10 w-40 rounded-md border border-border bg-background px-3"
                />
              </label>
              <Button
                variant="ghost"
                onClick={() => setSpeakers((all) => all.filter((x) => x.id !== sp.id))}
                aria-label={f.removeSpeaker(sp.name)}
              >
                {f.removeSpeaker(sp.name)}
              </Button>
            </div>
          ))}
          <div>
            <Button
              variant="outline"
              onClick={() =>
                setSpeakers((all) => [
                  ...all,
                  { id: `s${all.length + 1}`, name: f.speakerName(all.length + 1), camp: null },
                ])
              }
              disabled={speakers.length >= 8}
            >
              {f.addSpeaker}
            </Button>
          </div>
        </fieldset>
        <div className="flex gap-2">
          <Button variant="action" onClick={create} disabled={busy || !title.trim()}>
            {busy ? f.creating : f.create}
          </Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            {f.cancel}
          </Button>
        </div>
      </div>
    </Section>
  );
}

export function StudioView() {
  const { ws } = useParams<{ ws: string }>();
  const { data, error, mutate } = useSWR<ShowBrief[]>(`/workspaces/${ws}/studio`, fetcher);

  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-6 pb-24 lg:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-[70ch]">
          <h1 className="page-title">{s.list.title}</h1>
          <p className="mt-2 text-pretty text-muted-foreground">{s.list.lead}</p>
        </div>
        <NewShow ws={ws} onCreated={() => mutate()} />
      </header>

      {error ? (
        <LoadFailed onRetry={() => mutate()} />
      ) : !data ? (
        <p className="mt-8 flex items-center gap-2 text-muted-foreground">
          <IconCircleNotch className="size-4 animate-spin" aria-hidden /> {s.loadFailed}
        </p>
      ) : data.length === 0 ? (
        <div className="mt-8 rounded-md border border-dashed border-border p-8">
          <p className="font-bold">{s.list.empty}</p>
          <p className="mt-1 text-muted-foreground">{s.list.emptyHint}</p>
        </div>
      ) : (
        <ul className="mt-8 border-t border-foreground">
          {data.map((show, i) => (
            <li key={show.id} className="arrive border-b border-border" style={{ "--i": i } as React.CSSProperties}>
              <Link
                href={`/w/${ws}/studio/${show.id}` as never}
                className="grid gap-2 py-4 outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring sm:grid-cols-[minmax(0,1fr)_auto]"
              >
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-display text-lg font-bold">
                    <IconMicrophone className="size-4" aria-hidden />
                    <span className="text-pretty">{show.title}</span>
                    {show.is_demo && <DemoTag />}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                    <StatusDot status={show.status} />
                    {show.station && <span>{show.station}</span>}
                    <span>{s.list.claims(show.claims)}</span>
                    <span>{s.list.sent(show.sent)}</span>
                  </p>
                </div>
                <span className="self-center text-sm font-bold underline underline-offset-4">
                  {show.status === "ended" ? s.list.bilan : s.list.open}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
