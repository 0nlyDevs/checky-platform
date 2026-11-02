"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { IconCircleDashed, IconCircleNotch, IconRadio, IconShieldCheck, IconTimer, type Icon } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { VerdictChip } from "@/components/claims/verdict";
import { DemoTag, when } from "@/components/rubrique/bits";
import type { AntenneRow, FollowOut } from "@/components/rubrique/types";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const a = t.rubrique.antenne;

// Status is workflow, not truth: ink icons, never a verdict colour.
const STATUS_ICON: Record<AntenneRow["status"], Icon> = { new: IconCircleDashed, followed: IconTimer, checked: IconShieldCheck };

function Heard({ row }: { row: AntenneRow }) {
  const c = row.latest;
  const from = c.text_from === "pending" ? a.pending : c.text_from === "transcript" ? a.fromTranscript : a.fromVeilleur;
  return (
    <figure className="mt-2 text-sm">
      {c.heard_text ? <blockquote className="quote text-base text-pretty">« {c.heard_text} »</blockquote> : null}
      <figcaption className="mt-1 text-muted-foreground">
        {c.station} · {when(c.recorded_at)} · {from}
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
  const shown = limit ? rows.slice(0, limit) : rows;

  async function follow(row: AntenneRow) {
    setBusy(row.latest.id);
    try {
      const out = await api<FollowOut>(`/workspaces/${ws}/radio-clips/${row.latest.id}/follow`, { method: "POST", body: JSON.stringify({ item_id: row.item_id }) });
      toast(a.followed(out.ref ?? ""), {
        action: { label: a.open, onClick: () => router.push(`/w/${ws}/affirmations/${out.item_id}` as never) },
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

  if (shown.length === 0) return <p className="text-sm text-muted-foreground">{a.empty}</p>;

  return (
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
              {row.demo && <DemoTag />}
            </p>
            <p className="mt-1 font-bold text-pretty">{row.claim}</p>
            {row.stations.length > 1 && <p className="text-sm text-muted-foreground">{row.stations.join(" · ")}</p>}
            <Heard row={row} />
            {(row.item_id || actions) && (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                {row.item_id && (
                  <Link href={`/w/${ws}/affirmations/${row.item_id}` as never} className="text-sm font-bold underline underline-offset-4">
                    {row.ref ?? a.open}
                  </Link>
                )}
                {row.verdict && <VerdictChip verdict={row.verdict} />}
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
  );
}
