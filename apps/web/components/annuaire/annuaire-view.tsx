"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { GesturesCheck } from "@/components/annuaire/gestures-check";
import type { Contact } from "@/components/dossier/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconAddressBook, IconArrowSquareOut, IconCircleNotch, IconMagnifyingGlass, IconPhone, IconPlus, IconSealCheck, IconX } from "@/lib/icons";
import { cn } from "@/lib/utils";

const a = t.dossier.annuaire;
const KINDS = ["institution", "officer", "expert", "journalist", "person", "media", "page"] as const;
const LANGS = ["fr", "mg", "en"] as const;
const ALL = "";

const fieldClass =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";

function regionOf(c: Contact): string | null {
  const l = c.location ?? {};
  return typeof l.region === "string" && l.region ? l.region : typeof l.name === "string" && l.name ? l.name : null;
}

/** The API writes each official number the way its country writes it abroad (`display`). */
function showNumber(page: { url: string; display?: unknown }): string {
  return typeof page.display === "string" && page.display ? page.display : page.url.replace(/^tel:/, "");
}

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function ContactCard({ contact, editor, onVerify, onRemove }: { contact: Contact; editor: boolean; onVerify: () => void; onRemove: () => void }) {
  const place = regionOf(contact) ?? a.national;
  const asked = Number(contact.stats?.asked ?? 0);
  const answered = Number(contact.stats?.answered ?? 0);
  const declared = contact.official_pages.filter((p) => p.kind !== "phone");
  const numbers = contact.official_pages.filter((p) => p.kind === "phone");
  const pages = declared.length ? declared : contact.website ? [{ url: contact.website, verified: false }] : [];
  return (
    <li className="flex flex-col rounded-md border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-bold text-pretty">{contact.name}</p>
          <p className="text-sm text-muted-foreground">{[contact.role, contact.institution].filter(Boolean).join(" · ")}</p>
        </div>
        {contact.is_demo && <span className="shrink-0 rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted-foreground">{a.demo}</span>}
      </div>
      <p className="mt-2 text-sm">
        {place}
        {contact.languages.length > 0 && <span className="text-muted-foreground"> · {contact.languages.map((l) => a.languages[l] ?? l).join(", ")}</span>}
      </p>
      {contact.topics.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1 text-xs">
          {contact.topics.map((topic) => (
            <li key={topic} className="rounded-sm bg-muted px-1.5 py-0.5">
              {topic}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 space-y-1 text-sm">
        {(contact.phone || contact.whatsapp) && (
          <p className="flex flex-wrap items-center gap-x-3">
            <span className="font-display font-bold tabular">{contact.phone ?? contact.whatsapp}</span>
            {contact.phone && (
              <a href={`tel:${contact.phone.replace(/[^\d+]/g, "")}`} className="inline-flex items-center gap-1 underline decoration-border underline-offset-4 hover:decoration-foreground">
                <IconPhone className="size-3.5" aria-hidden />
                {t.dossier.who.call}
              </a>
            )}
          </p>
        )}
        {contact.email && (
          <p>
            <a href={`mailto:${contact.email}`} className="break-all underline decoration-border underline-offset-4 hover:decoration-foreground">
              {contact.email}
            </a>
          </p>
        )}
        {numbers.map((p) => (
          <p key={p.url} className="flex flex-wrap items-center gap-x-3">
            <span className="inline-flex items-center gap-1">
              {p.verified && <IconSealCheck className="size-3.5" aria-hidden />}
              {a.officialNumber}
              {p.verified && <span className="text-muted-foreground">({t.dossier.who.pageVerified})</span>}
            </span>
            <a href={p.url} className="font-display font-bold tabular underline decoration-border underline-offset-4 hover:decoration-foreground">
              {showNumber(p)}
            </a>
          </p>
        ))}
        {pages.map((p) => (
          <p key={p.url}>
            <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline decoration-border underline-offset-4 hover:decoration-foreground">
              {p.verified && <IconSealCheck className="size-3.5" aria-hidden />}
              {t.dossier.who.page}
              {p.verified && <span className="text-muted-foreground">({t.dossier.who.pageVerified})</span>}
              <IconArrowSquareOut className="size-3.5" aria-hidden />
            </a>
          </p>
        ))}
        {contact.hours && <p className="text-muted-foreground">{contact.hours}</p>}
      </div>
      <div className="mt-auto pt-3">
        <p className={cn("text-sm", contact.verified_at ? "font-bold" : "text-muted-foreground")}>
          {contact.verified_at ? a.verified : a.declared}
          {asked > 0 && <span className="font-normal text-muted-foreground"> · {a.answers(asked, answered)}</span>}
        </p>
        {!contact.own && <p className="text-sm text-muted-foreground">{a.shared}</p>}
        {editor && contact.own && (
          <div className="mt-2 flex flex-wrap gap-2">
            {!contact.verified_at && (
              <Button size="sm" variant="outline" onClick={onVerify}>
                <IconSealCheck aria-hidden />
                {a.verify}
              </Button>
            )}
            <Button size="icon-sm" variant="ghost" onClick={onRemove} aria-label={`${a.remove} ${contact.name}`} title={a.remove} className="ml-auto text-muted-foreground">
              <IconX aria-hidden />
            </Button>
          </div>
        )}
      </div>
    </li>
  );
}

function AddContact({ ws, onSaved, onCancel }: { ws: string; onSaved: () => void; onCancel: () => void }) {
  const [busy, setBusy] = useState(false);
  const f = a.fields;

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const text = (k: string) => String(form.get(k) ?? "").trim() || null;
    const website = text("website");
    const numbers = (text("numbers") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 6);
    setBusy(true);
    try {
      await api(`/workspaces/${ws}/contacts`, {
        method: "POST",
        body: JSON.stringify({
          name: text("name"),
          kind: text("kind") ?? "institution",
          institution: text("institution") ?? "",
          role: text("role") ?? "",
          topics: (text("topics") ?? "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
            .slice(0, 20),
          languages: form.getAll("languages").map(String),
          place: text("place"),
          phone: text("phone"),
          whatsapp: text("whatsapp"),
          email: text("email"),
          website,
          official_pages: [...(website ? [{ kind: "site", url: website }] : []), ...numbers.map((url) => ({ kind: "phone", url }))],
          hours: text("hours"),
          shared: form.has("shared"),
        }),
      });
      toast.success(a.saved);
      onSaved();
    } catch (err) {
      toast.error(err instanceof ApiError && err.status === 422 ? `${a.failed} (${err.message})` : a.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="grid gap-4 rounded-md border border-border bg-card p-4 md:grid-cols-2 md:p-5">
      <div className="space-y-1.5">
        <Label htmlFor="c-name">{f.name}</Label>
        <Input id="c-name" name="name" required maxLength={200} className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-kind">{f.kind}</Label>
        <select id="c-kind" name="kind" className={fieldClass} defaultValue="institution">
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {a.kinds[k]}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-institution">{f.institution}</Label>
        <Input id="c-institution" name="institution" maxLength={200} className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-role">{f.role}</Label>
        <Input id="c-role" name="role" maxLength={200} className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-topics">{f.topics}</Label>
        <Input id="c-topics" name="topics" maxLength={600} className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-place">{f.place}</Label>
        <Input id="c-place" name="place" maxLength={200} className="h-10" />
      </div>
      <fieldset className="space-y-1.5 md:col-span-2">
        <legend className="text-sm font-medium">{f.languages}</legend>
        <div className="flex flex-wrap gap-3">
          {LANGS.map((l) => (
            <label key={l} className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" name="languages" value={l} defaultChecked={l !== "en"} className="size-4 accent-foreground" />
              {a.languages[l]}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="space-y-1.5">
        <Label htmlFor="c-phone">{f.phone}</Label>
        <Input id="c-phone" name="phone" type="tel" pattern="\+?[0-9 \(\)\-]{3,60}" className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-whatsapp">{f.whatsapp}</Label>
        <Input id="c-whatsapp" name="whatsapp" type="tel" pattern="\+?[0-9 \(\)\-]{3,60}" className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-email">{f.email}</Label>
        <Input id="c-email" name="email" type="email" maxLength={200} className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-website">{f.website}</Label>
        <Input id="c-website" name="website" type="url" className="h-10" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-numbers">{f.officialNumbers}</Label>
        <Input id="c-numbers" name="numbers" inputMode="tel" maxLength={300} aria-describedby="c-numbers-hint" className="h-10" />
        <p id="c-numbers-hint" className="text-sm text-muted-foreground">
          {a.officialNumbersHint}
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="c-hours">{f.hours}</Label>
        <Input id="c-hours" name="hours" maxLength={200} className="h-10" />
      </div>
      <label className="inline-flex items-center gap-2 self-end text-sm">
        <input type="checkbox" name="shared" className="size-4 accent-foreground" />
        {f.shared}
      </label>
      <p className="text-sm text-muted-foreground md:col-span-2">{a.noPersonal}</p>
      <div className="flex gap-2 md:col-span-2">
        <Button type="submit" disabled={busy}>
          {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
          {busy ? a.saving : a.save}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {a.cancel}
        </Button>
      </div>
    </form>
  );
}

/** L'Annuaire: who can prove what, by topic and by region, with professional contacts only. */
export function AnnuaireView() {
  const { ws } = useParams<{ ws: string }>();
  const key = `/workspaces/${ws}/contacts`;
  const { data, error, mutate } = useSWR<Contact[]>(key, fetcher);
  const editor = true; // every journalist checks and removes the newsroom's own contacts
  const [q, setQ] = useState("");
  const [topic, setTopic] = useState(ALL);
  const [region, setRegion] = useState(ALL);
  const [adding, setAdding] = useState(false);

  const topics = useMemo(() => [...new Set((data ?? []).flatMap((c) => c.topics))].sort((x, y) => x.localeCompare(y, "fr")), [data]);
  const regions = useMemo(() => [...new Set((data ?? []).map(regionOf).filter((r): r is string => Boolean(r)))].sort((x, y) => x.localeCompare(y, "fr")), [data]);
  const shown = useMemo(() => {
    const needle = fold(q.trim());
    return (data ?? []).filter((c) => {
      if (topic && !c.topics.includes(topic)) return false;
      // A national contact answers for every region.
      if (region && regionOf(c) && regionOf(c) !== region) return false;
      if (!needle) return true;
      return fold([c.name, c.institution, c.role, ...c.topics].join(" ")).includes(needle);
    });
  }, [data, q, topic, region]);

  async function verify(c: Contact) {
    try {
      await api(`${key}/${c.id}/verify`, { method: "POST" });
      mutate();
    } catch {
      toast.error(a.failed);
    }
  }

  async function remove(c: Contact) {
    try {
      await api(`${key}/${c.id}`, { method: "DELETE" });
      toast(a.removed);
      mutate();
    } catch {
      toast.error(a.failed);
    }
  }

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-16 lg:px-8 lg:pt-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="page-title">{a.title}</h1>
          <p className="mt-2 max-w-[70ch] text-muted-foreground">{a.lead}</p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)} className="h-10">
            <IconPlus aria-hidden />
            {a.add}
          </Button>
        )}
      </header>

      {adding && (
        <div className="mt-6">
          <AddContact
            ws={ws}
            onCancel={() => setAdding(false)}
            onSaved={() => {
              setAdding(false);
              mutate();
            }}
          />
        </div>
      )}

      <GesturesCheck ws={ws} />

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <div className="relative min-w-60 flex-1">
          <Label htmlFor="annuaire-q" className="sr-only">
            {a.search}
          </Label>
          <IconMagnifyingGlass className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input id="annuaire-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={a.search} className="h-10 pl-9" />
        </div>
        <div>
          <Label htmlFor="annuaire-topic" className="sr-only">
            {a.allBeats}
          </Label>
          <select id="annuaire-topic" value={topic} onChange={(e) => setTopic(e.target.value)} className={cn(fieldClass, "w-auto")}>
            <option value={ALL}>{a.allBeats}</option>
            {topics.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="annuaire-region" className="sr-only">
            {a.allRegions}
          </Label>
          <select id="annuaire-region" value={region} onChange={(e) => setRegion(e.target.value)} className={cn(fieldClass, "w-auto")}>
            <option value={ALL}>{a.allRegions}</option>
            {regions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </div>
        {data && <p className="pb-2 text-sm text-muted-foreground tabular">{a.count(shown.length)}</p>}
      </div>

      {error && (
        <div className="mt-8">
          <p className="text-muted-foreground">{a.loadFailed}</p>
          <Button variant="outline" className="mt-3" onClick={() => mutate()}>
            {a.retry}
          </Button>
        </div>
      )}
      {!data && !error && (
        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      )}
      {data && shown.length === 0 && (
        <div className="mt-8 rounded-md border border-dashed border-border px-6 py-12 text-center">
          <IconAddressBook className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-2 text-muted-foreground">{a.empty}</p>
        </div>
      )}
      {data && shown.length > 0 && (
        // Grouped by kind, like Chiffres by theme: institutions first, the people and pages after.
        <div className="mt-10 space-y-12">
          {KINDS.map((kind) => [kind, shown.filter((c) => (KINDS.includes(c.kind as (typeof KINDS)[number]) ? c.kind : "institution") === kind)] as const)
            .filter(([, group]) => group.length > 0)
            .map(([kind, group]) => (
              <section key={kind} aria-labelledby={`kind-${kind}`}>
                <h2 id={`kind-${kind}`} className="flex items-baseline gap-2 border-b border-border pb-2 font-display text-xl font-bold">
                  {a.kindGroups[kind]}
                  <span className="text-base font-normal text-muted-foreground tabular">{group.length}</span>
                </h2>
                <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {group.map((c) => (
                    <ContactCard key={c.id} contact={c} editor={editor} onVerify={() => verify(c)} onRemove={() => remove(c)} />
                  ))}
                </ul>
              </section>
            ))}
        </div>
      )}
    </div>
  );
}
