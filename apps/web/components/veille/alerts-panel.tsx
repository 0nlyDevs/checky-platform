"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { IconArrowSquareOut, IconCaretRight, IconCircleNotch, IconMapPin, IconRadio, IconWarning } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DemoTag, KIND_ICON, when } from "@/components/rubrique/bits";
import type { Alert, AlertMember, Kind } from "@/components/rubrique/types";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";
import { AlertKitPanel } from "./alert-kit-panel";

const al = t.rubrique.alerts;

/** « Risque élevé » in ink: a danger level is not a verdict, so never a verdict colour. */
export function AlertLevel({ level, adjusted }: { level: string; adjusted?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-sm font-bold", level === "high" ? "border-2 border-foreground" : "border-border")}>
      <IconWarning className="size-4" aria-hidden />
      {al.level[level] ?? level}
      {adjusted && <span className="font-normal text-muted-foreground">· {al.adjusted}</span>}
    </span>
  );
}

function Facts({ alert }: { alert: Alert }) {
  const f = alert.facts;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
      <span className="font-bold text-foreground tabular">{al.reports(f.reports)}</span>
      {f.stations.length > 0 && (
        <span className="inline-flex items-center gap-1">
          <IconRadio className="size-3.5" aria-hidden />
          {al.radios(f.stations.length)}
        </span>
      )}
      {f.regions.length > 0 && (
        <span className="inline-flex items-center gap-1">
          <IconMapPin className="size-3.5" aria-hidden />
          {f.regions.join(", ")}
        </span>
      )}
      {f.hours !== null && <span className="tabular">{al.since(f.hours)}</span>}
      {alert.demo && <DemoTag />}
    </p>
  );
}

function MemberRow({ ws, m, picked, onPick }: { ws: string; m: AlertMember; picked?: boolean; onPick?: (on: boolean) => void }) {
  const kind = (m.kind in KIND_ICON ? m.kind : "item") as Kind;
  const Icon = KIND_ICON[kind];
  const title = m.item_id ? (
    <Link href={`/w/${ws}/claims/${m.item_id}` as never} className="font-bold text-pretty underline-offset-4 hover:underline">
      {m.title}
    </Link>
  ) : m.url ? (
    <a href={m.url} target="_blank" rel="noreferrer" className="font-bold text-pretty underline-offset-4 hover:underline">
      {m.title}
      <IconArrowSquareOut className="ml-1 inline size-3.5 align-[-0.1em]" aria-hidden />
    </a>
  ) : (
    <span className="font-bold text-pretty">{m.title}</span>
  );
  return (
    <li className="flex gap-3 py-2">
      {onPick && (
        <input
          type="checkbox"
          checked={picked}
          onChange={(e) => onPick(e.target.checked)}
          aria-label={al.select(m.title)}
          className="mt-1 size-4 shrink-0 accent-foreground"
        />
      )}
      <div className="min-w-0 text-sm">
        {title}
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Icon className="size-3.5" aria-hidden />
            {t.rubrique.kinds[kind]}
          </span>
          <time dateTime={m.at} className="tabular">
            {when(m.at)}
          </time>
          {m.station && <span>{m.station}</span>}
          {(m.place || m.region) && <span>{m.place ?? m.region}</span>}
          {m.demo && <DemoTag />}
        </p>
      </div>
    </li>
  );
}

function AlertCard({ ws, alert, others, onChanged }: { ws: string; alert: Alert; others: Alert[]; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState<"split" | "merge" | null>(null);
  const base = `/workspaces/${ws}/alerts/${alert.id}`;

  async function split() {
    if (picked.size >= alert.members.length) {
      toast.error(al.keepOne);
      return;
    }
    setBusy("split");
    try {
      const other = await api<Alert>(`${base}/split`, { method: "POST", body: JSON.stringify({ keys: [...picked] }) });
      toast(al.splitDone(other.ref ?? ""));
      setPicked(new Set());
      onChanged();
    } catch {
      toast.error(al.failed);
    } finally {
      setBusy(null);
    }
  }

  async function merge() {
    if (!target) return;
    setBusy("merge");
    try {
      const into = await api<Alert>(`${base}/merge`, { method: "POST", body: JSON.stringify({ other_id: target }) });
      const gone = others.find((o) => o.id === target);
      toast(al.merged(gone?.ref ? `${into.ref} (${gone.ref})` : (into.ref ?? "")));
      setTarget("");
      onChanged();
    } catch {
      toast.error(al.failed);
    } finally {
      setBusy(null);
    }
  }

  return (
    <li id={`alerte-${alert.id}`} className="scroll-mt-24 py-3 first:pt-0">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {alert.ref && <span className="font-display font-bold tabular">{alert.ref}</span>}
        <AlertLevel level={alert.level} adjusted={Boolean(alert.override)} />
      </p>
      <p className="mt-1.5 font-bold text-pretty">{alert.title}</p>
      <Facts alert={alert} />
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((x) => !x)}
        className="mt-2 inline-flex h-9 items-center gap-1.5 rounded-md text-sm font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <IconCaretRight className={cn("size-4 transition-transform", open && "rotate-90")} aria-hidden />
        {al.members}
      </button>
      {open && (
        <div className="mt-1">
          <p className="text-sm text-pretty text-muted-foreground">{al.splitHint}</p>
          <ul className="mt-1 divide-y divide-border">
            {alert.members.map((m) => (
              <MemberRow
                key={m.key}
                ws={ws}
                m={m}
                picked={picked.has(m.key)}
                onPick={(on) =>
                  setPicked((prev) => {
                    const next = new Set(prev);
                    if (on) next.add(m.key);
                    else next.delete(m.key);
                    return next;
                  })
                }
              />
            ))}
          </ul>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button variant="outline" size="lg" onClick={split} disabled={picked.size === 0 || busy !== null}>
              {busy === "split" && <IconCircleNotch className="animate-spin" aria-hidden />}
              {busy === "split" ? al.splitting : al.split}
            </Button>
          </div>
          {others.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Select value={target} onValueChange={setTarget}>
                <SelectTrigger aria-label={al.mergeWith} className="h-10 w-auto max-w-full min-w-48 bg-card">
                  <SelectValue placeholder={al.mergeWith} />
                </SelectTrigger>
                <SelectContent>
                  {others.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.ref ? `${o.ref} · ` : ""}
                      {o.title.length > 60 ? `${o.title.slice(0, 60)}…` : o.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="lg" onClick={merge} disabled={!target || busy !== null}>
                {busy === "merge" && <IconCircleNotch className="animate-spin" aria-hidden />}
                {busy === "merge" ? al.merging : al.merge}
              </Button>
            </div>
          )}
          <AlertKitPanel ws={ws} alertId={alert.id} onChanged={onChanged} />
        </div>
      )}
    </li>
  );
}

/**
 * Open alerts: variants of one dangerous rumour grouped by Checky across tips, SMS, radio and
 * dossiers. `actions` lets the desk split and merge (Veille); without it, a short list that
 * links to Veille (Ma rubrique).
 */
export function AlertsList({ ws, alerts, actions = false, limit, onChanged }: { ws: string; alerts: Alert[]; actions?: boolean; limit?: number; onChanged?: () => void }) {
  const open = alerts.filter((a) => a.state === "open");
  // Arriving from a badge (`#alerte-<id>`): the cards load after the browser looked for the anchor.
  const ready = actions && open.length > 0;
  useEffect(() => {
    if (!ready || !window.location.hash.startsWith("#alerte-")) return;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [ready]);
  if (open.length === 0) return <p className="text-sm text-muted-foreground">{al.empty}</p>;
  if (!actions) {
    return (
      <ul className="divide-y divide-border">
        {open.slice(0, limit).map((a) => (
          <li key={a.id} className="py-3 first:pt-0">
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {a.ref && <span className="font-display font-bold tabular">{a.ref}</span>}
              <AlertLevel level={a.level} adjusted={Boolean(a.override)} />
            </p>
            <Link href={`/w/${ws}/watch#alerte-${a.id}` as never} className="mt-1.5 block font-bold text-pretty underline-offset-4 hover:underline">
              {a.title}
            </Link>
            <Facts alert={a} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="divide-y divide-border">
      {open.map((a) => (
        <AlertCard key={a.id} ws={ws} alert={a} others={open.filter((o) => o.id !== a.id)} onChanged={() => onChanged?.()} />
      ))}
    </ul>
  );
}
