"use client";
import type { Item } from "@fanilo/shared";
import { useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { publication as t } from "@/lib/i18n/fr/publication";

type Route = { id: string; side: "rumour" | "truth"; channel: string; place: string; at: string; proof: { note: string } };
type Formats = { radio: string; sms: string; social: string };
export function RoutePanel({ item }: { item: Item }) {
  const path = `/workspaces/${item.workspace_id}/items/${item.id}`;
  const { data, mutate } = useSWR<Route[]>(`${path}/routes`, fetcher);
  const { data: formats } = useSWR<Formats>(item.status === "published" ? `${path}/diffusion` : null, fetcher);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState("");
  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(false); const form = e.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries());
    try { await api(`${path}/routes`, { method: "POST", body: JSON.stringify({ ...values, at: new Date().toISOString() }) }); form.reset(); await mutate(); }
    catch { setError(true); }
  }
  return <section className="mt-8 border-t border-border pt-6"><h2 className="font-display text-xl font-bold">{t.trail}</h2><p className="mt-2 text-sm text-muted-foreground">{t.trailHelp}</p>
    {!data?.length && <p className="mt-4 text-sm">{t.empty}</p>}
    {data && <ol className="mt-4 divide-y divide-border border-y border-border">{data.map(row => <li key={row.id} className="py-3"><strong>{row.side === "rumour" ? t.rumour : t.truth}</strong> · {row.channel} · {row.place}<p className="text-sm">{row.proof.note}</p><time className="text-xs text-muted-foreground" dateTime={row.at}>{new Date(row.at).toLocaleString("fr-FR")}</time></li>)}</ol>}
    <form onSubmit={add} className="mt-5 grid gap-3 sm:grid-cols-2">
      <label>{t.channel}<select name="channel" className="mt-1 block w-full rounded-md border border-input p-3">{["web", "facebook", "whatsapp", "tiktok", "radio", "sms", "press", "poster", "other"].map(x => <option key={x}>{x}</option>)}</select></label>
      <label>{t.trail}<select name="side" className="mt-1 block w-full rounded-md border border-input p-3"><option value="rumour">{t.rumour}</option>{item.status === "published" && <option value="truth">{t.truth}</option>}</select></label>
      <label>{t.place}<input name="place" required maxLength={300} className="mt-1 block w-full rounded-md border border-input p-3" /></label>
      <label>{t.proof}<input name="url" type="url" className="mt-1 block w-full rounded-md border border-input p-3" /></label>
      <label className="sm:col-span-2">{t.note}<textarea name="note" required minLength={5} maxLength={1000} rows={2} className="mt-1 block w-full rounded-md border border-input p-3" /></label>
      {error && <p role="alert">{t.error}</p>}<Button>{t.add}</Button>
    </form>
    {formats && <div className="mt-7 space-y-4"><h3 className="font-display text-lg font-bold">{t.formats}</h3><p className="text-sm text-muted-foreground">{t.formatsHelp}</p>{(["radio", "sms", "social"] as const).map(kind => <div key={kind} className="border-t border-border py-3"><h4 className="font-bold">{t[kind]}</h4><p className="my-2 whitespace-pre-wrap text-sm">{formats[kind]}</p><Button variant="outline" onClick={async () => { await navigator.clipboard.writeText(formats[kind]); setCopied(kind); }}>{copied === kind ? t.copied : t.copy}</Button></div>)}</div>}
  </section>;
}
