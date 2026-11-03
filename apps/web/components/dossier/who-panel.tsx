"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconAddressBook, IconArrowSquareOut, IconCheck, IconCircleNotch, IconCopy, IconPaperPlaneTilt, IconPhone, IconSealCheck } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { type Contact, fmtShort, type Question, type Who } from "./types";

const w = t.dossier.who;
const CHANNELS = ["whatsapp", "sms", "email", "call"] as const;
type Channel = (typeof CHANNELS)[number];

const fieldClass =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";

function firstChannel(c: Contact): Channel {
  if (c.whatsapp || c.phone) return "whatsapp";
  if (c.email) return "email";
  return "call";
}

/** The ready links for a prepared question: the journalist's own apps send, Checky sends nothing. */
function QuestionLinks({ q }: { q: Question }) {
  const [copied, setCopied] = useState(false);
  const order = q.channel === "email" ? ["mailto", "whatsapp", "sms", "tel"] : q.channel === "sms" ? ["sms", "whatsapp", "mailto", "tel"] : ["whatsapp", "sms", "mailto", "tel"];
  const ready = order.filter((k) => q.links[k]);
  return (
    <div className="flex flex-wrap gap-2">
      {ready.map((k, i) => (
        <Button key={k} asChild size="sm" variant={i === 0 ? "default" : "outline"}>
          <a href={q.links[k]} target={k === "whatsapp" ? "_blank" : undefined} rel="noreferrer">
            {k === "tel" ? <IconPhone aria-hidden /> : <IconArrowSquareOut aria-hidden />}
            {w.open[k] ?? k}
          </a>
        </Button>
      ))}
      <Button
        size="sm"
        variant="outline"
        onClick={async () => {
          await navigator.clipboard.writeText(q.message).catch(() => null);
          setCopied(true);
          toast.success(w.copied);
        }}
      >
        {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
        {w.copy}
      </Button>
    </div>
  );
}

function ContactCard({
  ws,
  itemId,
  contact,
  why,
  track,
  draft,
  asked,
  onAsked,
}: {
  ws: string;
  itemId: string;
  contact: Contact;
  why: string[];
  track: string | null;
  draft: string;
  asked: Question | null;
  onAsked: (q: Question) => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(draft);
  const [channel, setChannel] = useState<Channel>(firstChannel(contact));
  const [busy, setBusy] = useState(false);
  const [prepared, setPrepared] = useState<Question | null>(null);
  const page = contact.official_pages.find((p) => p.verified) ?? contact.official_pages[0];
  const site = page?.url ?? contact.website;
  const number = contact.phone ?? contact.whatsapp;
  const place = typeof contact.location.name === "string" ? contact.location.name : typeof contact.location.region === "string" ? contact.location.region : null;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const q = await api<Question>(`/workspaces/${ws}/items/${itemId}/questions`, {
        method: "POST",
        body: JSON.stringify({ contact_id: contact.id, question: text.trim(), channel }),
      });
      setPrepared(q);
      onAsked(q);
    } catch {
      toast.error(w.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-md border border-border bg-card p-4">
      <p className="font-bold text-pretty">
        {contact.name}
        {contact.is_demo && <span className="ml-1.5 rounded-sm border border-border px-1 text-xs font-normal text-muted-foreground">{w.demo}</span>}
      </p>
      <p className="text-sm text-muted-foreground">{[contact.role, contact.institution, place].filter(Boolean).join(" · ")}</p>
      {why.length > 0 && <p className="mt-2 text-sm text-pretty">{why.join(" · ")}</p>}
      {track && <p className="mt-1 text-sm text-muted-foreground">{track}</p>}
      <div className="mt-2 space-y-1 text-sm">
        {site && (
          <a href={site} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline decoration-border underline-offset-4 hover:decoration-foreground">
            {page?.verified && <IconSealCheck className="size-3.5" aria-hidden />}
            {w.page}
            {page?.verified && <span className="text-muted-foreground">({w.pageVerified})</span>}
            <IconArrowSquareOut className="size-3.5" aria-hidden />
          </a>
        )}
        {number && <p className="font-display font-bold tabular">{number}</p>}
      </div>

      {asked && !prepared ? (
        <p className="mt-3 text-sm">
          {asked.answered_at ? (
            <>
              <span className="font-bold">{w.answered}</span>
              {asked.answer?.stance && ` : ${w.stances[asked.answer.stance] ?? asked.answer.stance}`} · {fmtShort(asked.answered_at)}
            </>
          ) : (
            <span className="text-muted-foreground">
              {w.waiting} · {fmtShort(asked.sent_at)}
            </span>
          )}
        </p>
      ) : null}

      {prepared ? (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-pretty">{w.sentLead}</p>
          <QuestionLinks q={prepared} />
        </div>
      ) : open ? (
        <form onSubmit={send} className="mt-3 space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor={`q-${contact.id}`}>{w.question}</Label>
            <textarea id={`q-${contact.id}`} rows={5} minLength={10} maxLength={2000} required value={text} onChange={(e) => setText(e.target.value)} className={cn(fieldClass, "resize-y text-sm")} />
          </div>
          <fieldset>
            <legend className="text-sm font-medium">{w.channel}</legend>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {CHANNELS.map((c) => (
                <label key={c} className="inline-flex cursor-pointer items-center gap-1.5 rounded-sm border border-border px-2 py-1 text-sm has-checked:border-foreground has-checked:font-bold">
                  <input type="radio" name={`ch-${contact.id}`} value={c} checked={channel === c} onChange={() => setChannel(c)} className="size-3.5 accent-foreground" />
                  {w.channels[c]}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={busy || text.trim().length < 10}>
              {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPaperPlaneTilt aria-hidden />}
              {busy ? w.sending : w.send}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              {w.cancel}
            </Button>
          </div>
        </form>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            <IconPaperPlaneTilt aria-hidden />
            {w.ask}
          </Button>
          {contact.phone && (
            <Button asChild size="sm" variant="ghost">
              <a href={`tel:${contact.phone.replace(/[^\d+]/g, "")}`}>
                <IconPhone aria-hidden />
                {w.call}
              </a>
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

/** « Qui peut le prouver ? »: for each missing point, the people best placed to settle it. */
export function WhoPanel({ ws, itemId }: { ws: string; itemId: string }) {
  const key = `/workspaces/${ws}/items/${itemId}/who`;
  const { data, error, mutate } = useSWR<Who>(key, fetcher);
  const lastAsked = new Map<string, Question>();
  for (const q of data?.questions ?? []) if (q.contact_id) lastAsked.set(q.contact_id, q);
  const shown = new Set<string>();

  return (
    <section aria-labelledby="who" className="space-y-4">
      <header>
        <h2 id="who" className="font-display text-lg font-bold">
          {w.title}
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{w.lead}</p>
      </header>

      {!data && !error && <Skeleton className="h-40 w-full" />}
      {error && <p className="text-sm text-muted-foreground">{w.failed}</p>}

      {data?.points.map((p, i) => {
        // A contact appears once, under the first point it settles.
        const contacts = p.contacts.filter((c) => !shown.has(c.contact.id));
        contacts.forEach((c) => shown.add(c.contact.id));
        if (!contacts.length) return null;
        return (
          <div key={i} className="space-y-2">
            <h3 className="text-sm text-pretty">
              <span className="font-bold">{p.point ? w.point : w.whole}</span>
              {p.point && <span className="text-muted-foreground"> · {p.point}</span>}
            </h3>
            <ul className="space-y-3">
              {contacts.map((c) => (
                <ContactCard
                  key={c.contact.id}
                  ws={ws}
                  itemId={itemId}
                  contact={c.contact}
                  why={c.why}
                  track={c.track}
                  draft={c.question}
                  asked={lastAsked.get(c.contact.id) ?? null}
                  onAsked={() => mutate()}
                />
              ))}
            </ul>
          </div>
        );
      })}

      {data && shown.size === 0 && <p className="text-sm text-muted-foreground">{w.none}</p>}

      {data && data.questions.length > 0 && (
        <div>
          <h3 className="text-sm font-bold">{w.asked}</h3>
          <ul className="mt-1.5 space-y-1.5 text-sm">
            {data.questions.map((q) => (
              <li key={q.id} className="flex flex-wrap justify-between gap-x-3">
                <span>
                  {q.contact ?? "—"} · {w.channels[q.channel] ?? q.channel}
                </span>
                <span className={q.answered_at ? "font-bold" : "text-muted-foreground"}>
                  {q.answered_at ? `${w.answered}${q.answer?.stance ? ` : ${w.stances[q.answer.stance] ?? q.answer.stance}` : ""}` : w.waiting}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Link href={`/w/${ws}/directory`} className="inline-flex items-center gap-1.5 text-sm underline decoration-border underline-offset-4 hover:decoration-foreground">
        <IconAddressBook className="size-4" aria-hidden />
        {w.annuaire}
      </Link>
    </section>
  );
}
