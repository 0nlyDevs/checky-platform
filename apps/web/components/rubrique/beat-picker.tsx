"use client";

import { useState } from "react";
import { toast } from "sonner";
import { IconCheck, IconCircleNotch } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";
import type { Prefs } from "./types";

const p = t.rubrique.picker;

function Chips({ label, offered, chosen, onToggle }: { label: string; offered: string[]; chosen: string[]; onToggle: (v: string) => void }) {
  return (
    <fieldset>
      <legend className="font-bold">{label}</legend>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {offered.map((v) => {
          const on = chosen.includes(v);
          return (
            <button
              key={v}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(v)}
              className={cn(
                "inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                on ? "border-foreground bg-foreground font-bold text-background" : "border-input bg-card hover:border-foreground",
              )}
            >
              {on && <IconCheck className="size-3.5" aria-hidden />}
              {v}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/** My beats and places: what circulates there comes first on the morning page. */
export function BeatPicker({ ws, prefs, onSaved, onCancel }: { ws: string; prefs: Prefs; onSaved: (p: Prefs) => void; onCancel: () => void }) {
  const [beats, setBeats] = useState(prefs.beats);
  const [regions, setRegions] = useState(prefs.regions);
  const [saving, setSaving] = useState(false);
  const toggle = (set: React.Dispatch<React.SetStateAction<string[]>>) => (v: string) => set((xs) => (xs.includes(v) ? xs.filter((x) => x !== v) : [...xs, v]));
  const regionsOffered = [...new Set([...prefs.regions_offered, ...prefs.regions])];

  async function save() {
    setSaving(true);
    try {
      const out = await api<Prefs>(`/workspaces/${ws}/me/prefs`, {
        method: "PUT",
        body: JSON.stringify({ beats, regions, language: prefs.language, station: prefs.station }),
      });
      toast(p.saved);
      onSaved(out);
    } catch {
      toast.error(p.failed);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-md border border-foreground bg-card p-4 sm:p-5">
      <h2 className="font-display text-lg font-bold">{p.title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{beats.length + regions.length === 0 ? p.none : p.lead}</p>
      <div className="mt-4 space-y-4">
        <Chips label={p.beats} offered={prefs.beats_offered} chosen={beats} onToggle={toggle(setBeats)} />
        <Chips label={p.regions} offered={regionsOffered} chosen={regions} onToggle={toggle(setRegions)} />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <Button size="lg" onClick={save} disabled={saving}>
          {saving && <IconCircleNotch className="animate-spin" aria-hidden />}
          {saving ? p.saving : p.save}
        </Button>
        <Button size="lg" variant="ghost" onClick={onCancel} disabled={saving}>
          {p.cancel}
        </Button>
      </div>
    </div>
  );
}
