"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { api, ApiError, fetcher } from "@/lib/api";
import { locale, t as messages } from "@/lib/i18n/live";

const t = messages.resources;

type Kind = "contacts" | "registry" | "figures" | "radio";
type Field = keyof typeof t.fields;
type Row = { id: string; name?: string; role?: string; institution?: string; phone?: string; email?: string; website?: string; verified_at?: string; title?: string; issuer?: string; text?: string; url?: string; label?: string; value?: string; unit?: string; as_of?: string; country?: string; source_name?: string; source_url?: string; station?: string; heard_text?: string; recorded_at?: string; language?: string };
const fields: Record<Kind, Field[]> = {
  contacts: ["name", "role", "institution", "phone", "email", "website"],
  registry: ["issuer", "title", "number", "url", "text"],
  figures: ["topic", "label", "value", "unit", "as_of", "country", "source_name", "source_url"],
  radio: ["station", "heard_text", "language", "recorded_at", "source_id"],
};
const optional: Field[] = ["role", "institution", "phone", "email", "website", "number", "unit", "country", "source_id"];
const endpoints: Record<Kind, string> = { contacts: "contacts", registry: "registry", figures: "figures", radio: "radio-clips" };
const inputClass = "mt-1 w-full rounded-md border border-input bg-background p-3 text-base focus-visible:outline-2 focus-visible:outline-ring";

function SafeLink({ url, children }: { url?: string; children: React.ReactNode }) {
  if (!url || !/^https?:\/\//i.test(url)) return null;
  return <a href={url} target="_blank" rel="noreferrer" className="font-semibold underline underline-offset-4">{children}</a>;
}

export function ResourceView({ kind }: { kind: Kind }) {
  const { ws } = useParams<{ ws: string }>();
  const endpoint = `/workspaces/${ws}/${endpoints[kind]}`;
  const { data, error, mutate } = useSWR<Row[]>(endpoint, fetcher);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [search, setSearch] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setFailure("");
    const form = event.currentTarget;
    const values: Record<string, string | null> = {};
    const submitted = new FormData(form);
    for (const key of fields[kind]) {
      const value = String(submitted.get(key) || "").trim();
      if (value) values[key] = key === "recorded_at" ? new Date(value).toISOString() : value;
    }
    try { await api(endpoint, { method: "POST", body: JSON.stringify(values) }); await mutate(); setAdding(false); }
    catch (e) { setFailure(e instanceof ApiError && e.status === 403 ? t.denied : t.error); }
    finally { setBusy(false); }
  }
  const shown = (data ?? []).filter(row => Object.values(row).join(" ").toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <main className="mx-auto max-w-4xl px-4 py-8 lg:px-8">
    <h1 className="page-title">{t[kind].title}</h1><p className="mt-3 max-w-prose text-lg text-muted-foreground">{t[kind].lead}</p>
    <div className="my-6 flex flex-wrap items-end gap-3"><label className="min-w-0 flex-1 text-sm font-semibold">{t.search}<input className={inputClass} value={search} onChange={e => setSearch(e.target.value)} /></label><Button size="lg" onClick={() => setAdding(!adding)}>{adding ? t.cancel : t.new}</Button></div>
    {adding && <form onSubmit={save} className="mb-8 space-y-4 rounded-md border border-border p-5">
      {fields[kind].map(field => <label key={field} className="block text-sm font-semibold" htmlFor={field}>{t.fields[field]}
        {["text", "heard_text"].includes(field) ? <textarea id={field} name={field} rows={5} required maxLength={field === "text" ? 30000 : 4000} className={inputClass} /> : <input id={field} name={field} required={!optional.includes(field)} type={field === "recorded_at" ? "datetime-local" : field === "email" ? "email" : ["website", "url", "source_url"].includes(field) ? "url" : "text"} defaultValue={field === "language" ? "mg" : undefined} maxLength={field === "source_id" ? 36 : 500} className={inputClass} />}
      </label>)}
      {failure && <p role="alert">{failure}</p>}<Button type="submit" disabled={busy}>{busy ? t.saving : t.save}</Button>
    </form>}
    {error && <div role="alert"><p>{t.failed}</p><Button variant="outline" onClick={() => void mutate()}>{t.retry}</Button></div>}
    {data && !shown.length && <p className="border-t border-border py-8 text-muted-foreground">{t.empty}</p>}
    <ul className="divide-y divide-border border-t border-border">{shown.map(row => <li key={row.id} className="space-y-3 py-6">
      <h2 className="font-display text-xl font-bold">{row.name || row.title || row.label || row.station}</h2>
      {kind === "contacts" && <><p>{[row.role, row.institution].filter(Boolean).join(" · ")}</p><p className="text-sm text-muted-foreground">{t.unknown}</p><div className="flex flex-wrap gap-4">{row.phone && <a href={`tel:${row.phone.replace(/[^+0-9]/g, "")}`} className="underline">{t.call} · {row.phone}</a>}{row.email && <a href={`mailto:${row.email}`} className="underline">{t.email}</a>}<SafeLink url={row.website}>{t.source}</SafeLink></div></>}
      {kind === "registry" && <><p>{row.issuer}</p><details><summary className="cursor-pointer">{t.fields.text}</summary><p className="mt-2 whitespace-pre-wrap text-sm">{row.text}</p></details><SafeLink url={row.url}>{t.source}</SafeLink></>}
      {kind === "figures" && <><p className="text-2xl font-semibold tabular-nums">{row.value} {row.unit}</p><p>{[row.country, row.as_of, row.source_name].filter(Boolean).join(" · ")}</p><SafeLink url={row.source_url}>{t.source}</SafeLink></>}
      {kind === "radio" && <><p className="whitespace-pre-wrap">{row.heard_text}</p><p className="text-sm text-muted-foreground">{row.language} · {row.recorded_at && new Date(row.recorded_at).toLocaleString(locale())}</p><Link className="font-semibold underline" href={`/w/${ws}/verifier?lien=${encodeURIComponent(row.heard_text || "")}`}>{t.check}</Link></>}
    </li>)}</ul>
  </main>;
}
