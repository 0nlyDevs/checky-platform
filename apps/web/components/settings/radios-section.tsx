"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { MG_REGIONS } from "@/components/settings/regions";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { IconBroadcast, IconCheck, IconCircleNotch, IconCopy, IconPlus, IconX } from "@/lib/icons";

const r = t.team.settings.radios;
const day = dateFormat({ day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
const field =
  "mt-1 h-10 w-full rounded-md border border-input bg-background px-3 outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15";

type Radio = {
  id: string;
  name: string;
  frequency: string | null;
  location: { name?: string; region?: string };
  is_demo: boolean;
  link: string;
  broadcasts: number;
  last_broadcast_at: string | null;
};

/** « Radios partenaires »: each radio's link to today's flashes, and how many it marked aired. */
export function RadiosSection({ ws, canEdit }: { ws: string; canEdit: boolean }) {
  const path = `/workspaces/${ws}/radios`;
  const { data, mutate } = useSWR<Radio[]>(path, fetcher);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    try {
      await api(path, {
        method: "POST",
        body: JSON.stringify({
          name: String(form.get("name")).trim(),
          frequency: String(form.get("frequency") || "").trim() || null,
          region: String(form.get("region") || "") || null,
        }),
      });
      formEl.reset();
      await mutate();
    } catch {
      toast.error(r.failed);
    } finally {
      setBusy(false);
    }
  }

  async function remove(radio: Radio) {
    setConfirming(null);
    try {
      await api(`${path}/${radio.id}`, { method: "DELETE" });
      toast.success(r.removed(radio.name));
      await mutate();
    } catch {
      toast.error(r.failed);
    }
  }

  return (
    <section aria-labelledby="radios-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="radios-title" className="font-display text-lg font-bold">
        {r.title}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{r.lead}</p>
      {data && !data.length && <p className="mt-4 text-sm">{r.empty}</p>}
      {!!data?.length && (
        <ul className="mt-4 divide-y divide-border rounded-md border border-border">
          {data.map((radio) => (
            <li key={radio.id} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-4 py-3">
              <div className="min-w-0 flex-1 basis-60">
                <p className="font-medium">
                  {radio.name}
                  {radio.frequency && <span className="text-muted-foreground"> · {radio.frequency}</span>}
                  {radio.is_demo && !/démo/i.test(radio.name) && <span className="ml-2 rounded-sm border border-border px-1.5 text-xs text-muted-foreground">{r.demo}</span>}
                </p>
                {(radio.location.region || radio.location.name) && (
                  <p className="text-sm text-muted-foreground">{[radio.location.name, radio.location.region].filter(Boolean).join(" · ")}</p>
                )}
                <p className="mt-1 flex items-center gap-1.5 text-sm">
                  <IconBroadcast className="size-4 shrink-0" aria-hidden />
                  {r.aired(radio.broadcasts)}
                  {radio.last_broadcast_at && <span className="text-muted-foreground">, {r.lastAired(day.format(new Date(radio.last_broadcast_at)))}</span>}
                </p>
                <p className="mt-1 truncate text-xs text-muted-foreground" title={radio.link}>
                  <span className="sr-only">{r.link} : </span>
                  {radio.link}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="h-9"
                  onClick={() =>
                    navigator.clipboard?.writeText(radio.link).then(() => {
                      setCopied(radio.id);
                      toast.success(r.copied);
                    })
                  }
                >
                  {copied === radio.id ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
                  {r.copy}
                </Button>
                {canEdit &&
                  (confirming === radio.id ? (
                    <Button variant="destructive" className="h-9" onClick={() => remove(radio)} onBlur={() => setConfirming(null)} autoFocus>
                      {r.removeConfirm}
                    </Button>
                  ) : (
                    <Button variant="outline" className="h-9" onClick={() => setConfirming(radio.id)} aria-label={r.remove(radio.name)}>
                      <IconX aria-hidden />
                    </Button>
                  ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <form onSubmit={add} className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)_minmax(0,1fr)_auto] sm:items-end">
          <label className="block">
            <span className="text-sm font-medium">{r.name}</span>
            <input name="name" required maxLength={120} placeholder={r.namePlaceholder} className={field} />
          </label>
          <label className="block">
            <span className="text-sm font-medium">{r.frequency}</span>
            <input name="frequency" maxLength={40} placeholder={r.frequencyPlaceholder} className={field} />
          </label>
          <label className="block">
            <span className="text-sm font-medium">{r.region}</span>
            <select name="region" defaultValue="" className={field}>
              <option value="">—</option>
              {MG_REGIONS.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" variant="outline" className="h-10" disabled={busy}>
            {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPlus aria-hidden />}
            {busy ? r.adding : r.add}
          </Button>
        </form>
      ) : (
        null
      )}
    </section>
  );
}
