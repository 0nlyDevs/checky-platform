"use client";

import type { Item } from "@checky/shared";
import Link from "next/link";
import { useEffect, useState } from "react";
import { IconCircleNotch, IconPlus } from "@/lib/icons";
import { toast } from "sonner";
import { StatusLabel, toClaim, VerdictBadge } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/live";

function localTimeValue(d: Date) {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function NewClaimSheet({ ws, nextRef, onCreated }: { ws: string; nextRef: string; onCreated: (item: Item) => void }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [origin, setOrigin] = useState("facebook");
  const [title, setTitle] = useState("");
  const [similar, setSimilar] = useState<Item[]>([]);

  // While the claim is typed, warn if the desk already follows one with the same words.
  useEffect(() => {
    const q = title.trim();
    if (q.length < 8) return;
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const found = await api<{ score: number; item: Item }[]>(`/workspaces/${ws}/items/similar?q=${encodeURIComponent(q)}`);
        if (live) setSimilar(found.map((s) => s.item));
      } catch {
        // Only a warning: without it the form works as before.
      }
    }, 400);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [ws, title]);
  const shown = title.trim().length < 8 ? [] : similar;

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const [h, m] = String(form.get("seen")).split(":").map(Number);
    const seen = new Date();
    if (!Number.isNaN(h)) seen.setHours(h, m || 0, 0, 0);
    // A time later than now means yesterday evening.
    if (seen.getTime() > Date.now()) seen.setDate(seen.getDate() - 1);
    setPending(true);
    setError(null);
    try {
      const item = await api<Item>(`/workspaces/${ws}/items`, {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title")).trim(),
          body: String(form.get("context") ?? "").trim(),
          type: "claim",
          status: "to_check",
          data: { ref: nextRef, first_seen_at: seen.toISOString(), origin, source_count: 0 },
        }),
      });
      onCreated(item);
      setTitle("");
      setSimilar([]);
      toast.success(`${t.claims.form.added} · ${nextRef}`);
      setOpen(false);
    } catch {
      setError(t.auth.errors.generic);
    } finally {
      setPending(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="action" size="lg" className="size-11 px-0 sm:h-10 sm:w-auto sm:px-4" aria-label={t.claims.newClaim}>
          <IconPlus className="size-5 sm:size-4" aria-hidden />
          <span className="hidden sm:inline">{t.claims.newClaim}</span>
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b border-border p-5">
          <SheetTitle className="text-lg">{t.claims.form.title}</SheetTitle>
          <SheetDescription>{t.claims.form.lead}</SheetDescription>
        </SheetHeader>
        <form id="new-claim" onSubmit={onSubmit} className="flex-1 space-y-5 overflow-y-auto p-5">
          <div className="space-y-2">
            <Label htmlFor="claim-title">{t.claims.form.claim}</Label>
            <textarea
              id="claim-title"
              name="title"
              required
              maxLength={300}
              rows={3}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              aria-describedby={shown.length ? "claim-similar" : undefined}
              placeholder={t.claims.form.claimPlaceholder}
              className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
            />
          </div>
          {shown.length > 0 && (
            <div id="claim-similar" role="status" className="rounded-md border border-border bg-muted p-3.5">
              <p className="text-sm font-medium">{t.claims.form.similarTitle}</p>
              <p className="mt-0.5 text-sm text-pretty text-muted-foreground">{t.claims.form.similarLead}</p>
              <ul className="mt-3 space-y-2.5">
                {shown.map((item) => {
                  const c = toClaim(item);
                  return (
                    <li key={item.id} className="rounded-md border border-border bg-card p-3">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="font-display text-base font-semibold tracking-wide tabular">{c.ref}</span>
                        <Link
                          href={`/w/${ws}/claims/${item.id}`}
                          onClick={() => setOpen(false)}
                          className="text-sm font-medium underline underline-offset-2"
                        >
                          {t.claims.form.similarOpen}
                        </Link>
                      </div>
                      <p className="mt-1 text-pretty">{item.title}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                        <StatusLabel status={c.status} />
                        {(c.verdict || c.suggested) && <VerdictBadge claim={c} compact />}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="claim-seen">{t.claims.form.seenAt}</Label>
              <Input
                id="claim-seen"
                name="seen"
                type="time"
                defaultValue={localTimeValue(new Date())}
                className="h-10 tabular"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="claim-origin">{t.claims.form.origin}</Label>
              <Select value={origin} onValueChange={setOrigin}>
                <SelectTrigger id="claim-origin" className="h-10 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(t.origins).map(([k, label]) => (
                    <SelectItem key={k} value={k}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="claim-context">{t.claims.form.context}</Label>
            <textarea
              id="claim-context"
              name="context"
              rows={3}
              placeholder={t.claims.form.contextPlaceholder}
              className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
            />
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-verdict-false-soft px-3 py-2.5 text-sm text-verdict-false-ink">
              {error}
            </p>
          )}
        </form>
        <SheetFooter className="flex-row justify-end gap-2 border-t border-border p-4">
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            {t.claims.form.cancel}
          </Button>
          <Button type="submit" form="new-claim" disabled={pending}>
            {pending && <IconCircleNotch className="animate-spin" aria-hidden />}
            {t.claims.form.submit}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
