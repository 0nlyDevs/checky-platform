"use client";
import type { Item, Verdict } from "@fanilo/shared";
import { VERDICTS } from "@fanilo/shared";
import { useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { publication as t } from "@/lib/i18n/fr/publication";
import { VERDICT_META } from "./verdict";

type Settings = { settings: { double_signature: boolean; ai_enabled: boolean } };
export function PublicationPanel({ item, onSaved }: { item: Item; onSaved: (item: Item) => void }) {
  const base = `/workspaces/${item.workspace_id}`;
  const { data: workspace } = useSWR<Settings>(base, fetcher);
  const initial = item.data.verdict ?? item.data.verdict_suggested;
  const [verdict, setVerdict] = useState<Verdict>(VERDICTS.includes(initial as Verdict) ? initial as Verdict : "unverifiable");
  const [reason, setReason] = useState(typeof item.data.reason === "string" ? item.data.reason : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function sign(publish: boolean) {
    setBusy(true); setError(false);
    try { onSaved(await api<Item>(`${base}/items/${item.id}/sign`, { method: "POST", body: JSON.stringify({ verdict, reason, publish }) })); }
    catch { setError(true); } finally { setBusy(false); }
  }
  async function release() {
    setBusy(true); setError(false);
    try { onSaved(await api<Item>(`${base}/items/${item.id}`, { method: "PATCH", body: JSON.stringify({ status: "published" }) })); }
    catch { setError(true); } finally { setBusy(false); }
  }
  return <section className="mt-6 space-y-3 border-t border-border pt-5"><h3 className="font-display text-lg font-bold">{t.title}</h3><p className="text-sm text-muted-foreground">{t.lead}</p>
    <label className="block text-sm font-semibold">{t.verdict}<select value={verdict} onChange={e => setVerdict(e.target.value as Verdict)} className="mt-1 block w-full rounded-md border border-input bg-background p-3">{VERDICTS.map(v => <option key={v} value={v}>{VERDICT_META[v].label}</option>)}</select></label>
    <label className="block text-sm font-semibold">{t.reason}<textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} maxLength={2000} className="mt-1 block w-full rounded-md border border-input bg-background p-3" /></label>
    {workspace?.settings.double_signature && <p className="text-sm">{t.double}</p>}
    {typeof item.data.signed_by === "string" && <p className="text-sm">{t.signed} · {String(item.data.signed_at || "")}</p>}
    {error && <p role="alert">{t.failed}</p>}
    <div className="flex flex-wrap gap-3"><Button disabled={busy || reason.trim().length < 10} onClick={() => void sign(!workspace?.settings.double_signature)}>{busy ? t.saving : workspace?.settings.double_signature ? t.sign : t.publish}</Button>
      {workspace?.settings.double_signature && !!item.data.signed_by && item.status !== "published" && <Button variant="outline" disabled={busy} onClick={() => void release()}>{t.release}</Button>}
    </div>
  </section>;
}

export function NewsroomRules({ ws }: { ws: string }) {
  const path = `/workspaces/${ws}`;
  const { data, mutate } = useSWR<Settings>(path, fetcher);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(false);
    const form = new FormData(e.currentTarget);
    try { await api(path, { method: "PATCH", body: JSON.stringify({ settings: { double_signature: form.has("double"), ai_enabled: form.has("ai") } }) }); await mutate(); }
    catch { setError(true); } finally { setBusy(false); }
  }
  return <section className="rounded-md border border-border p-5"><h2 className="font-semibold">{t.settings}</h2><p className="mt-1 text-sm text-muted-foreground">{t.settingsHelp}</p>{data && <form key={JSON.stringify(data.settings)} onSubmit={save} className="mt-4 space-y-3">
    <label className="flex items-center gap-3"><input type="checkbox" name="double" defaultChecked={data.settings.double_signature} className="size-4" />{t.doubleToggle}</label>
    <label className="flex items-center gap-3"><input type="checkbox" name="ai" defaultChecked={data.settings.ai_enabled} className="size-4" />{t.aiToggle}</label>
    {error && <p role="alert">{t.failed}</p>}<Button disabled={busy}>{t.save}</Button>
  </form>}</section>;
}
