"use client";
import { useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { dossier } from "@/lib/i18n/fr/dossier";
import { publication as t } from "@/lib/i18n/fr/publication";
import { IconBroadcast, IconMinusCircle, IconStamp } from "@/lib/icons";
import { cn } from "@/lib/utils";

type Settings = { settings: { ai_enabled: boolean } };

const s = dossier.sign.strip;

/**
 * What leaves the newsroom, in three tiers: what the public can already see, what this signature
 * adds, and what never leaves (the reading, its percentage, the dossier, its questions).
 */
export function PublicStrip({ className }: { className?: string }) {
  const rows = [
    { icon: IconBroadcast, label: s.visible, text: s.visibleText },
    { icon: IconStamp, label: s.after, text: s.afterText },
    { icon: IconMinusCircle, label: s.never, text: s.neverText },
  ];
  return (
    <section aria-label={s.label} className={cn("rounded-md border border-border bg-card", className)}>
      <ul className="grid divide-y divide-border md:grid-cols-3 md:divide-x md:divide-y-0">
        {rows.map(({ icon: Icon, label, text }) => (
          <li key={label} className="flex gap-2.5 p-3 text-sm">
            <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p className="text-pretty">
              <span className="font-bold">{label}</span> : {text}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function NewsroomRules({ ws }: { ws: string }) {
  const path = `/workspaces/${ws}`;
  const { data, mutate } = useSWR<Settings>(path, fetcher);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(false);
    const form = new FormData(e.currentTarget);
    try { await api(path, { method: "PATCH", body: JSON.stringify({ settings: { ai_enabled: form.has("ai") } }) }); await mutate(); }
    catch { setError(true); } finally { setBusy(false); }
  }
  return <section className="rounded-md border border-border p-5"><h2 className="font-display text-lg font-bold">{t.settings}</h2><p className="mt-1 text-sm text-muted-foreground">{t.settingsHelp}</p>{data && <form key={JSON.stringify(data.settings)} onSubmit={save} className="mt-4 space-y-3">

    <label className="flex items-center gap-3"><input type="checkbox" name="ai" defaultChecked={data.settings.ai_enabled} className="size-4" />{t.aiToggle}</label>
    {error && <p role="alert">{t.failed}</p>}<Button disabled={busy}>{t.save}</Button>
  </form>}</section>;
}
