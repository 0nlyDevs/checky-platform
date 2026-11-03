"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { IconCircleDashed, IconCircleNotch, IconRadio, IconShieldCheck, IconTimer, IconWarning, type Icon } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { VerdictChip } from "@/components/claims/verdict";
import { DemoTag, when } from "@/components/rubrique/bits";
import type { AntenneRow, FollowOut } from "@/components/rubrique/types";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

const a = t.rubrique.antenne;

// Status is workflow, not truth: ink icons, never a verdict colour.
const STATUS_ICON: Record<AntenneRow["status"], Icon> = { new: IconCircleDashed, followed: IconTimer, checked: IconShieldCheck };

function Heard({ row }: { row: AntenneRow }) {
  const c = row.latest;
  const from = c.text_from === "pending" ? a.pending : c.text_from === "transcript" ? a.fromTranscript : a.fromVeilleur;
  return (
    <figure className="mt-2 text-sm">
      {c.heard_text ? <blockquote className="quote text-base text-pretty">{t.common.quote(c.heard_text)}</blockquote> : null}
      <figcaption className="mt-1 text-muted-foreground">
        {row.credit ?? `${c.station} · ${when(c.recorded_at)}`} · {from}
        {c.language === "mg" && c.text_from === "veilleur" && <span className="block">{a.mgNote}</span>}
      </figcaption>
    </figure>
  );
}

/**
 * À l'antenne: radio clips grouped by claim, the most reported first. `actions` adds Suivre (opens
 * or joins a dossier, each clip a stop on the rumour's route) and Ignorer.
 */
export function AntenneList({
  ws,
  rows,
  actions = false,
  limit,
  onChanged,
}: {
  ws: string;
  rows: AntenneRow[];
  actions?: boolean;
  limit?: number;
  onChanged?: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [region, setRegion] = useState("");
  const [station, setStation] = useState("");
  const [topic, setTopic] = useState("");
  const regions = [...new Set(rows.flatMap((r) => r.regions ?? []))].sort();
  const stations = [...new Set(rows.flatMap((r) => r.stations))].sort();
  const needle = topic.trim().toLowerCase();
  const filtered = rows.filter(
    (r) =>
      (!region || (r.regions ?? []).includes(region)) &&
      (!station || r.stations.includes(station)) &&
      (!needle || r.claim.toLowerCase().includes(needle) || r.latest.heard_text.toLowerCase().includes(needle)),
  );
  const shown = limit ? filtered.slice(0, limit) : filtered;

  /** Plays the station's recording from the second the passage starts (first tap loads it). */
  function play(row: AntenneRow) {
    const c = row.latest;
    if (!row.audio_url) return;
    const audio = new Audio(row.audio_url);
    audio.currentTime = Math.max(0, c.clip_at_s ?? 0);
    void audio.play().catch(() => toast.error(a.failed));
    setBusy(c.id);
    audio.addEventListener("ended", () => setBusy(null), { once: true });
    audio.addEventListener("error", () => setBusy(null), { once: true });
    window.setTimeout(() => setBusy((now) => (now === c.id ? null : now)), 60_000);
  }

  async function follow(row: AntenneRow) {
    setBusy(row.latest.id);
    try {
      const out = await api<FollowOut>(`/workspaces/${ws}/radio-clips/${row.latest.id}/follow`, { method: "POST", body: JSON.stringify({ item_id: row.item_id }) });
      toast(a.followed(out.ref ?? ""), {
        action: { label: a.open, onClick: () => router.push(`/w/${ws}/claims/${out.item_id}` as never) },
      });
      onChanged?.();
    } catch {
      toast.error(a.failed);
    } finally {
      setBusy(null);
    }
  }

  async function ignore(row: AntenneRow) {
    setBusy(row.latest.id);
    try {
      for (const id of row.clip_ids) await api(`/workspaces/${ws}/radio-clips/${id}/ignore`, { method: "POST" });
      toast(a.ignored);
      onChanged?.();
    } catch {
      toast.error(a.failed);
    } finally {
      setBusy(null);
    }
  }

  const filters = (
    <div className="mb-3 flex flex-wrap items-end gap-2 text-sm">
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">{a.filterRegion}</span>
        <select
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          className="rounded-md border border-border bg-card px-2 py-1.5"
        >
          <option value="">{a.filterAll}</option>
          {regions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">{a.filterStation}</span>
        <select
          value={station}
          onChange={(e) => setStation(e.target.value)}
          className="rounded-md border border-border bg-card px-2 py-1.5"
        >
          <option value="">{a.filterAll}</option>
          {stations.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">{a.filterTopic}</span>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder={a.filterTopicPlaceholder}
          className="rounded-md border border-border bg-card px-2 py-1.5"
        />
      </label>
    </div>
  );

  if (shown.length === 0)
    return (
      <>
        {filters}
        <p className="text-sm text-muted-foreground">{a.empty}</p>
      </>
    );

  return (
    <>
      {filters}
      <ul className="divide-y divide-border">
      {shown.map((row, i) => {
        const Status = STATUS_ICON[row.status];
        const working = busy === row.latest.id;
        return (
          <li key={row.latest.id} className="arrive py-3 first:pt-0" style={{ "--i": Math.min(i, 8) } as React.CSSProperties}>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="inline-flex items-center gap-1.5">
                <Status className={cn("size-4", row.status === "new" ? "text-muted-foreground" : "text-foreground")} aria-hidden />
                {a.status[row.status]}
              </span>
              <span className="inline-flex items-center gap-1.5 font-bold tabular">
                <IconRadio className="size-4" aria-hidden />
                {a.reports(row.reports)}
              </span>
              {row.regions_24h.length > 0 && <span className="text-muted-foreground">{row.regions_24h.join(", ")}</span>}
              {row.alert && (
                <Link href={`/w/${ws}/watch#alerte-${row.alert.id}` as never} className="inline-flex items-center gap-1 font-bold underline-offset-4 hover:underline">
                  <IconWarning className="size-4" aria-hidden />
                  {t.rubrique.alerts.badge(row.alert.ref ?? "")}
                </Link>
              )}
              {row.demo && <DemoTag />}
            </p>
            <p className="mt-1 font-bold text-pretty">{row.claim}</p>
            {row.stations.length > 1 && <p className="text-sm text-muted-foreground">{row.stations.join(" · ")}</p>}
            <Heard row={row} />
            {(row.item_id || actions) && (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                {row.item_id && (
                  <Link href={`/w/${ws}/claims/${row.item_id}` as never} className="text-sm font-bold underline underline-offset-4">
                    {row.ref ?? a.open}
                  </Link>
                )}
                {row.verdict && <VerdictChip verdict={row.verdict} />}
                {row.audio_url && (
                  <Button variant="ghost" size="lg" onClick={() => play(row)}>
                    {a.play}
                  </Button>
                )}
                {actions && row.status === "new" && (
                  <>
                    <Button variant="outline" size="lg" onClick={() => follow(row)} disabled={working}>
                      {working && <IconCircleNotch className="animate-spin" aria-hidden />}
                      {working ? a.following : a.follow}
                    </Button>
                    <Button variant="ghost" size="lg" onClick={() => ignore(row)} disabled={working}>
                      {a.ignore}
                    </Button>
                  </>
                )}
              </div>
            )}
          </li>
        );
      })}
      </ul>
    </>
  );
}
