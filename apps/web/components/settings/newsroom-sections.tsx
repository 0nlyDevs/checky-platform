"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { MG_REGIONS, type NewsroomSettings, TIMEZONES, type WorkspaceDetail } from "@/components/settings/regions";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconCircleNotch, IconPlus, IconX } from "@/lib/icons";

const b = t.team.settings.beats;
const pl = t.team.settings.place;
const field =
  "h-10 w-full rounded-md border border-input bg-background px-3 outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15";

/** The workspace with its settings; both sections write through the same PATCH, which merges. */
function useNewsroom(ws: string) {
  const path = `/workspaces/${ws}`;
  const swr = useSWR<WorkspaceDetail>(path, fetcher);
  const save = (settings: Partial<NewsroomSettings>) =>
    swr.mutate(api<WorkspaceDetail>(path, { method: "PATCH", body: JSON.stringify({ settings }) }), { revalidate: false });
  return { ...swr, save };
}

/** « Rubriques »: the beats a newsroom follows, as chips; each change is saved at once. */
export function BeatsSection({ ws }: { ws: string }) {
  const { data, save } = useNewsroom(ws);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const beats = data?.settings.beats ?? [];

  async function write(next: string[]) {
    setBusy(true);
    try {
      await save({ beats: next });
      toast.success(b.saved);
    } catch {
      toast.error(b.failed);
    } finally {
      setBusy(false);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const beat = draft.trim().toLowerCase();
    if (!beat) return;
    if (beat.length > 40) return toast.error(b.tooLong);
    if (!beats.includes(beat)) await write([...beats, beat]);
    setDraft("");
  }

  return (
    <section aria-labelledby="beats-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="beats-title" className="font-semibold">
        {b.title}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{b.lead}</p>
      {data && (
        <>
          {beats.length ? (
            <ul className="mt-4 flex flex-wrap gap-2">
              {beats.map((beat) => (
                <li key={beat} className="inline-flex h-9 items-center gap-1 rounded-sm border border-foreground pr-1 pl-3 text-sm font-bold">
                  {beat}
                  <button
                    type="button"
                    disabled={busy || beats.length === 1}
                    onClick={() => write(beats.filter((x) => x !== beat))}
                    aria-label={b.remove(beat)}
                    className="grid size-7 place-items-center rounded-sm outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40"
                  >
                    <IconX className="size-4" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm">{b.empty}</p>
          )}
          <form onSubmit={add} className="mt-4 flex flex-wrap items-end gap-2">
            <label className="block min-w-0 flex-1 basis-48">
              <span className="text-sm font-medium">{b.label}</span>
              <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={b.placeholder} maxLength={60} className={`mt-1 ${field}`} />
            </label>
            <Button type="submit" variant="outline" className="h-10" disabled={busy || !draft.trim()}>
              {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPlus aria-hidden />}
              {b.add}
            </Button>
          </form>
        </>
      )}
    </section>
  );
}

/** « Lieu et heure »: the newsroom's time zone (today's flashes), country and home region. */
export function PlaceSection({ ws }: { ws: string }) {
  const { data, save } = useNewsroom(ws);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await save({
        timezone: String(form.get("timezone") || "").trim(),
        country: String(form.get("country") || "").trim(),
        region: String(form.get("region") || "") || null,
      });
      toast.success(pl.saved);
    } catch {
      toast.error(pl.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="place-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="place-title" className="font-semibold">
        {pl.title}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{pl.lead}</p>
      {data && (
        <form key={JSON.stringify(data.settings)} onSubmit={submit} className="mt-4 grid gap-4 sm:grid-cols-3">
          <label className="block">
            <span className="text-sm font-medium">{pl.timezone}</span>
            <input name="timezone" list="timezones" defaultValue={data.settings.timezone} required maxLength={60} className={`mt-1 ${field}`} />
            <datalist id="timezones">
              {TIMEZONES.map((z) => (
                <option key={z} value={z} />
              ))}
            </datalist>
          </label>
          <label className="block">
            <span className="text-sm font-medium">{pl.country}</span>
            <input name="country" defaultValue={data.settings.country} required maxLength={80} className={`mt-1 ${field}`} />
          </label>
          <label className="block">
            <span className="text-sm font-medium">{pl.region}</span>
            <select name="region" defaultValue={data.settings.region ?? ""} className={`mt-1 ${field}`}>
              <option value="">{pl.regionNone}</option>
              {MG_REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <div className="sm:col-span-3">
            <Button type="submit" variant="outline" className="h-10" disabled={busy}>
              {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
              {pl.save}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
