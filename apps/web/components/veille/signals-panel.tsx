"use client";

import { useCallback, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconCircleNotch, IconPlus, IconX } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Signal } from "@/components/rubrique/types";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";

const s = t.rubrique.signals;

export type SignalMatched = { word: string; where: string; item_id?: string | null; excerpt?: string };

/** The toast a `signal.matched` event raises: the word, where it was heard or read, the excerpt. */
export function useSignalToasts(onMatch?: () => void) {
  return useCallback(
    (p: SignalMatched) => {
      toast(s.matched(p.word, s.where[p.where] ?? s.whereOther), { description: p.excerpt });
      onMatch?.();
    },
    [onMatch],
  );
}

/** Mots surveillés: words the newsroom wants to hear about the moment they pass on air or in print. */
export function SignalsPanel({ ws }: { ws: string }) {
  const key = `/workspaces/${ws}/signals`;
  const { data, mutate } = useSWR<Signal[]>(key, fetcher);
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const w = word.trim();
    if (!w) return;
    setBusy(true);
    try {
      await api(key, { method: "POST", body: JSON.stringify({ word: w }) });
      setWord("");
      toast(s.added(w));
      void mutate();
    } catch (err) {
      toast.error(err instanceof ApiError && err.status === 409 ? s.duplicate : s.failed);
    } finally {
      setBusy(false);
    }
  }

  async function remove(sig: Signal) {
    void mutate((xs) => xs?.filter((x) => x.id !== sig.id), { revalidate: false });
    try {
      await api(`${key}/${sig.id}`, { method: "DELETE" });
    } catch {
      toast.error(s.failed);
    }
    void mutate();
  }

  return (
    <div>
      <form onSubmit={add} className="flex gap-2">
        <Input value={word} onChange={(e) => setWord(e.target.value)} placeholder={s.placeholder} aria-label={s.label} maxLength={80} className="h-10 bg-card" />
        <Button type="submit" variant="outline" size="xl" className="h-10 px-3" disabled={busy || !word.trim()}>
          {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPlus aria-hidden />}
          {s.add}
        </Button>
      </form>
      {data && data.length === 0 && <p className="mt-3 text-sm text-muted-foreground">{s.empty}</p>}
      {data && data.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {data.map((sig) => (
            <li key={sig.id} className="inline-flex h-9 items-center gap-2 rounded-md border border-foreground bg-card pr-1 pl-3 text-sm">
              <span className="font-bold">{sig.word}</span>
              <span className="text-muted-foreground tabular">{s.hits(sig.hits)}</span>
              <button
                type="button"
                onClick={() => remove(sig)}
                aria-label={s.remove(sig.word)}
                className="grid size-7 place-items-center rounded-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
              >
                <IconX className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
