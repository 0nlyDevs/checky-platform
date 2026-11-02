"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { resources as t } from "@/lib/i18n/fr/resources";

type Desk = { interests: { beats: string[] }; items: { id: string; title: string; updated_at: string; tags: string[] }[] };
export function RubriqueView() {
  const { ws } = useParams<{ ws: string }>();
  const endpoint = `/workspaces/${ws}/rubrique`;
  const { data, error, mutate } = useSWR<Desk>(endpoint, fetcher);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState(false);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setFailure(false);
    const beats = String(new FormData(e.currentTarget).get("beats") || "").split(",").map(s => s.trim()).filter(Boolean);
    try { await api(endpoint, { method: "PUT", body: JSON.stringify({ beats }) }); await mutate(); }
    catch { setFailure(true); } finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-4xl px-4 py-8 lg:px-8"><h1 className="page-title">{t.rubrique}</h1><p className="mt-3 text-lg text-muted-foreground">{t.rubriqueLead}</p>
    <Link className="my-6 inline-block rounded-md bg-foreground px-5 py-3 font-bold text-background" href={`/w/${ws}/verifier`}>{t.verify}</Link>
    {data && <form onSubmit={save} className="mb-8 flex flex-wrap items-end gap-3"><label className="flex-1 text-sm font-semibold">{t.beats}<input key={data.interests.beats.join(",")} name="beats" defaultValue={data.interests.beats.join(", ")} className="mt-1 block w-full rounded-md border border-input p-3" /></label><Button disabled={busy}>{busy ? t.saving : t.save}</Button></form>}
    {(error || failure) && <p role="alert">{t.failed}</p>}
    <ul className="divide-y divide-border border-y border-border">{data?.items.map(i => <li key={i.id} className="py-5"><p className="text-xs text-muted-foreground">{new Date(i.updated_at).toLocaleDateString("fr-FR")} · {i.tags.join(" · ")}</p><Link className="mt-1 block font-display text-xl font-bold hover:underline" href={`/w/${ws}/affirmations/${i.id}`}>{i.title}</Link></li>)}</ul>
    {data && !data.items.length && <p className="py-6">{t.empty}</p>}
    <h2 className="mt-8 font-display text-xl font-bold">{t.shelves}</h2><nav className="mt-3 flex flex-wrap gap-5">{[["annuaire", t.contacts.title], ["documents", t.documents], ["chiffres", t.figures.title], ["angles", t.angles]].map(([path, label]) => <Link key={path} href={`/w/${ws}/${path}`} className="font-semibold underline underline-offset-4">{label}</Link>)}</nav>
  </main>;
}
