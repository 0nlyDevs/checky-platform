"use client";

import type { Item } from "@fanilo/shared";
import { useState } from "react";
import { LoaderCircle, Plus } from "lucide-react";
import { toast } from "sonner";
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
import { t } from "@/lib/i18n/fr";

function localTimeValue(d: Date) {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function NewClaimSheet({ ws, nextRef, onCreated }: { ws: string; nextRef: string; onCreated: (item: Item) => void }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [origin, setOrigin] = useState("facebook");

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
        <Button size="lg" className="h-10">
          <Plus aria-hidden />
          {t.claims.newClaim}
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
              placeholder={t.claims.form.claimPlaceholder}
              className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
            />
          </div>
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
            {pending && <LoaderCircle className="animate-spin" aria-hidden />}
            {t.claims.form.submit}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
