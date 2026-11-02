"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconArrowSquareOut, IconCircleNotch, IconGlobe, IconNewspaper, IconPhone, IconStamp } from "@/lib/icons";

const g = t.dossier.annuaire.check;

type Gesture = { kind: string; status: string; text: string; subject: string; proof: Record<string, unknown> };

const ICONS: Record<string, typeof IconGlobe> = {
  attribution: IconStamp,
  official_page: IconGlobe,
  number: IconPhone,
  press_article: IconNewspaper,
};

/** « Est-ce bien eux ? »: a message, a link or a number set against the Annuaire and the registry
 * (who it speaks for, its page, its numbers, the outlet's headline). Facts only, no model. */
export function GesturesCheck({ ws }: { ws: string }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [facts, setFacts] = useState<Gesture[] | null>(null);
  const [failed, setFailed] = useState(false);

  async function run(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const raw = value.trim();
    if (!raw) return;
    const link = /^https?:\/\/\S+$/i.test(raw);
    setBusy(true);
    setFailed(false);
    try {
      setFacts(await api<Gesture[]>(`/workspaces/${ws}/gestures`, { method: "POST", body: JSON.stringify(link ? { url: raw } : { text: raw }) }));
    } catch {
      setFacts(null);
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="gestures-title" className="mt-6 rounded-md border border-border bg-card p-4 md:p-5">
      <h2 id="gestures-title" className="font-bold">
        {g.title}
      </h2>
      <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">{g.lead}</p>
      <form onSubmit={run} className="mt-3">
        <label htmlFor="gestures-text" className="sr-only">
          {g.label}
        </label>
        <textarea
          id="gestures-text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          maxLength={6000}
          placeholder={g.placeholder}
          className="block w-full rounded-md border border-input bg-background p-3 outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
        />
        <Button type="submit" disabled={busy || !value.trim()} className="mt-2 h-10">
          {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
          {busy ? g.running : g.run}
        </Button>
      </form>
      <div aria-live="polite">
        {failed && <p className="mt-3 text-sm text-muted-foreground">{g.failed}</p>}
        {facts && facts.length === 0 && <p className="mt-3 text-sm text-muted-foreground">{g.nothing}</p>}
        {facts && facts.length > 0 && (
          <ul className="mt-3 divide-y divide-border border-y border-border">
            {facts.map((f, i) => {
              const Icon = ICONS[f.kind] ?? IconGlobe;
              const url = typeof f.proof.url === "string" && /^https?:\/\//.test(f.proof.url) ? f.proof.url : null;
              const declared = Array.isArray(f.proof.declared) ? (f.proof.declared as string[]) : [];
              return (
                <li key={`${f.kind}-${i}`} className="flex gap-3 py-3">
                  <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <div className="min-w-0 text-sm">
                    <p className="text-muted-foreground">
                      {g.kinds[f.kind] ?? f.kind}
                      {f.subject && (
                        <>
                          {" · "}
                          <span className={f.kind === "number" ? "font-display font-bold tabular text-foreground" : "break-all text-foreground"}>{f.subject}</span>
                        </>
                      )}
                    </p>
                    <p className="mt-0.5 font-bold text-pretty">{f.text}</p>
                    {declared.length > 0 && <p className="mt-0.5 font-display tabular">{g.declared(declared.join(", "))}</p>}
                    {url && (
                      <a href={url} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex items-center gap-1 underline decoration-border underline-offset-4 hover:decoration-foreground">
                        {g.open}
                        <IconArrowSquareOut className="size-3.5" aria-hidden />
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{g.note}</p>
    </section>
  );
}
