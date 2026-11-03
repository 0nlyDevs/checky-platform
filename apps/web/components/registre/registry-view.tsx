"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, ApiError, fetcher } from "@/lib/api";
import {
  IconAddressBook,
  IconArrowSquareOut,
  IconCheck,
  IconCircleNotch,
  IconCopy,
  IconDownloadSimple,
  IconPlus,
  IconSealCheck,
  IconStamp,
  IconX,
} from "@/lib/icons";
import { cn } from "@/lib/utils";
import { RegistryDiff } from "./registry-diff";
import { fieldClass, Tag } from "./ui";
import { type Communique, communiqueRef, frenchDay, type MatchResult, type SealKey, type SealResult } from "./types";
import { t } from "@/lib/i18n/live";

const r = t.registre;

const TABS = [
  { key: "originaux", get label() { return r.page.tabs.originals; } },
  { key: "faux", get label() { return r.page.tabs.fakes; } },
  { key: "reseau", get label() { return r.page.tabs.network; }, desk: true },
  { key: "cles", get label() { return r.page.tabs.keys; }, writer: true },
] as const;
type Tab = (typeof TABS)[number]["key"];


function failure(e: unknown) {
  if (e instanceof ApiError && e.code === "seal_unavailable") return r.seal.unavailable;
  if (e instanceof ApiError && e.status === 403) return r.page.denied;
  return r.page.failed;
}

/** « N° 2026-118 · JIRAMA · publié le 1er novembre 2026 » */
function RefLine({ c }: { c: Pick<Communique, "number" | "issuer" | "issued_on"> }) {
  return (
    <p className="font-display text-sm font-bold tabular-nums">
      {[c.number && r.entry.number(c.number), c.issuer, c.issued_on && r.entry.issued(frenchDay(c.issued_on))]
        .filter(Boolean)
        .join(" · ")}
    </p>
  );
}

function svgUrl(svg: string) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** The QR to print on the communiqué, with its link, a download and what a seal proves. */
function SealPanel({ seal, c }: { seal: SealResult; c: Communique }) {
  const [copied, setCopied] = useState(false);
  const name = `sceau-${(c.number || c.issuer).replace(/[^\w-]+/g, "-")}.svg`;
  function download() {
    const url = URL.createObjectURL(new Blob([seal.qr_svg], { type: "image/svg+xml" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function copy() {
    await navigator.clipboard.writeText(seal.sealed.url);
    setCopied(true);
    toast.success(r.seal.copied);
  }
  return (
    <div className="arrive mt-4 grid gap-5 rounded-md border border-foreground bg-card p-4 sm:grid-cols-[11rem_minmax(0,1fr)]">
      {/* eslint-disable-next-line @next/next/no-img-element -- an inline SVG data URL, nothing to optimise */}
      <img src={svgUrl(seal.qr_svg)} alt={r.seal.qrAlt(communiqueRef(c))} className="size-44 bg-white" />
      <div className="min-w-0 space-y-3">
        <div>
          <h4 className="font-display text-lg font-bold">{r.seal.title}</h4>
          <p className="text-sm text-muted-foreground">
            {r.seal.key(seal.sealed.key_id)} · {r.seal.sealedAt(frenchDay(seal.sealed.sealed_at))}
          </p>
        </div>
        <p className="max-w-prose text-sm">{r.seal.lead}</p>
        <p className="max-w-prose text-sm font-bold">{r.seal.proves}</p>
        {!seal.public && <p className="max-w-prose rounded-sm bg-muted p-2 text-sm">{r.seal.notPublic}</p>}
        <code className="block truncate rounded-sm bg-muted px-2 py-1 text-xs" title={seal.sealed.url}>
          {seal.sealed.url}
        </code>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={download}>
            <IconDownloadSimple aria-hidden />
            {r.seal.download}
          </Button>
          <Button variant="outline" onClick={copy}>
            {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
            {r.seal.copy}
          </Button>
          <Button variant="ghost" asChild>
            <a href={seal.sealed.url} target="_blank" rel="noreferrer">
              <IconArrowSquareOut aria-hidden />
              {r.seal.open}
            </a>
          </Button>
        </div>
      </div>
    </div>
  );
}

function OriginalRow({
  c,
  ws,
  canSeal,
  canConfirm,
  onChanged,
}: {
  c: Communique;
  ws: string;
  canSeal: boolean;
  canConfirm: boolean;
  onChanged: () => void;
}) {
  const [seal, setSeal] = useState<SealResult | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const path = `/workspaces/${ws}/registry/${c.id}`;

  async function sealIt() {
    setBusy(true);
    try {
      const done = await api<SealResult>(`${path}/seal`, { method: "POST" });
      setSeal(done);
      setOpen(true);
      if (!c.sealed) toast.success(r.seal.done);
      onChanged();
    } catch (e) {
      toast.error(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function showSeal() {
    if (open) return setOpen(false);
    if (seal) return setOpen(true);
    setBusy(true);
    try {
      setSeal(await api<SealResult>(`${path}/seal`));
      setOpen(true);
    } catch (e) {
      toast.error(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    setBusy(true);
    try {
      await api(`${path}/confirm`, { method: "POST" });
      toast.success(r.entry.confirmedToast);
      onChanged();
    } catch (e) {
      toast.error(failure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li id={`c-${c.id}`} className="py-5">
      <RefLine c={c} />
      <h3 className="mt-1 text-lg leading-snug font-bold text-pretty">{c.title}</h3>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {c.is_demo && <Tag strong>{r.entry.demo}</Tag>}
        {c.sealed && (
          <Tag strong>
            <IconSealCheck className="size-3.5" aria-hidden />
            {r.entry.sealed}
          </Tag>
        )}
        <Tag>{c.confirmed ? r.entry.confirmed : r.entry.confirmations(c.confirmations)}</Tag>
        {c.fakes > 0 && <Tag>{r.entry.fakes(c.fakes)}</Tag>}
        {!c.own && c.newsroom && <Tag>{r.entry.by(c.newsroom.name)}</Tag>}
      </div>
      <details className="mt-3 group">
        <summary className="cursor-pointer text-sm font-bold underline-offset-4 hover:underline">{r.entry.text}</summary>
        <p className="mt-2 max-w-prose rounded-sm bg-muted p-3 text-sm whitespace-pre-wrap">{c.text}</p>
        {c.url && /^https?:\/\//i.test(c.url) && (
          <a href={c.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm font-bold underline underline-offset-4">
            {r.entry.source}
            <IconArrowSquareOut className="size-4" aria-hidden />
          </a>
        )}
      </details>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {c.own && c.sealed && (
          <Button variant="outline" onClick={showSeal} disabled={busy} aria-expanded={open}>
            {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconStamp aria-hidden />}
            {open ? r.entry.hideSeal : r.entry.showSeal}
          </Button>
        )}
        {c.own && !c.sealed && canSeal && (
          <Button onClick={sealIt} disabled={busy}>
            {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconStamp aria-hidden />}
            {busy ? r.entry.sealing : r.entry.seal}
          </Button>
        )}
        {!c.own && canConfirm && !c.confirmed_by_us && (
          <>
            <Button variant="outline" onClick={confirm} disabled={busy}>
              <IconCheck aria-hidden />
              {r.entry.confirm}
            </Button>
            <p className="w-full text-sm text-muted-foreground">{r.entry.confirmHelp}</p>
          </>
        )}
        {!c.own && c.confirmed_by_us && <Tag strong>{r.entry.confirmedByUs}</Tag>}
      </div>
      {open && seal && <SealPanel seal={seal} c={c} />}
    </li>
  );
}

function FakeRow({ c }: { c: Communique }) {
  return (
    <li id={`c-${c.id}`} className="space-y-3 py-5">
      <div>
        <p className="font-display text-sm font-bold">
          {r.entry.fakeTitle} · {r.entry.caught(frenchDay(c.created_at))}
        </p>
        <h3 className="mt-1 text-lg leading-snug font-bold text-pretty">{r.entry.imitates(communiqueRef(c))}</h3>
        <p className="mt-1 text-muted-foreground">« {c.title} »</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {c.is_demo && <Tag strong>{r.entry.demo}</Tag>}
          {!c.own && c.newsroom && <Tag>{r.entry.by(c.newsroom.name)}</Tag>}
        </div>
      </div>
      <RegistryDiff diff={c.diff} summary={c.summary} changedNumbers={c.changed_numbers} />
      {c.url && /^https?:\/\//i.test(c.url) && (
        <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-bold underline underline-offset-4">
          {r.entry.fakeText}
          <IconArrowSquareOut className="size-4" aria-hidden />
        </a>
      )}
    </li>
  );
}

function KeysList({ ws }: { ws: string }) {
  const { data, mutate } = useSWR<SealKey[]>(`/workspaces/${ws}/registry/keys`, fetcher);
  const [asking, setAsking] = useState<string | null>(null);
  async function revoke(key: SealKey) {
    setAsking(null);
    try {
      await api(`/workspaces/${ws}/registry/keys/${key.key_id}/revoke`, { method: "POST" });
      toast.success(r.keys.revokedToast);
      mutate();
    } catch (e) {
      toast.error(failure(e));
    }
  }
  return (
    <div>
      <p className="max-w-prose text-muted-foreground">{r.keys.lead}</p>
      {data && !data.length && <p className="mt-4 border-t border-border py-6 text-muted-foreground">{r.keys.empty}</p>}
      <ul className="mt-4 divide-y divide-border border-t border-foreground">
        {data?.map((k) => (
          <li key={k.key_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-4">
            <div className="min-w-0 flex-1">
              <p className="font-bold">{k.issuer}</p>
              <p className="font-display text-sm font-bold tabular-nums">{k.key_id}</p>
              <p className="text-sm text-muted-foreground">
                {r.keys.created(frenchDay(k.created_at))} · {r.keys.seals(k.seals)} ·{" "}
                {k.revoked_at ? r.keys.revoked(frenchDay(k.revoked_at)) : r.keys.active}
              </p>
            </div>
            {!k.revoked_at &&
              (asking === k.key_id ? (
                <div className="flex gap-2">
                  <Button variant="destructive" onClick={() => revoke(k)}>
                    {r.keys.confirmRevoke}
                  </Button>
                  <Button variant="ghost" onClick={() => setAsking(null)}>
                    {r.keys.cancel}
                  </Button>
                </div>
              ) : (
                <Button variant="outline" onClick={() => setAsking(k.key_id)}>
                  {r.keys.revoke}
                </Button>
              ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

function OriginalForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const value = (k: string) => String(form.get(k) || "").trim() || null;
    const body = {
      issuer: value("issuer"),
      number: value("number"),
      issued_on: value("issued_on"),
      title: value("title"),
      place: value("place"),
      url: value("url"),
      text: value("text"),
    };
    try {
      await api(`/workspaces/${ws}/registry`, { method: "POST", body: JSON.stringify(body) });
      toast.success(r.form.saved);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError && e.status === 422 ? r.form.invalid : failure(e));
    } finally {
      setBusy(false);
    }
  }
  const today = new Date().toISOString().slice(0, 10);
  return (
    <form onSubmit={save} className="arrive mb-8 space-y-4 rounded-md border border-foreground bg-card p-5" aria-labelledby="original-form">
      <div>
        <h2 id="original-form" className="font-display text-xl font-bold">
          {r.form.title}
        </h2>
        <p className="mt-1 max-w-prose text-sm text-muted-foreground">{r.form.lead}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-bold">
          {r.form.issuer}
          <input name="issuer" required maxLength={200} placeholder={r.form.issuerHint} className={fieldClass} />
        </label>
        <label className="block text-sm font-bold">
          {r.form.number}
          <input name="number" maxLength={60} placeholder="2026-118" className={cn(fieldClass, "tabular-nums")} />
        </label>
        <label className="block text-sm font-bold">
          {r.form.issuedOn}
          <input name="issued_on" type="date" max={today} className={fieldClass} />
        </label>
        <label className="block text-sm font-bold">
          {r.form.place}
          <input name="place" maxLength={200} className={fieldClass} />
        </label>
      </div>
      <label className="block text-sm font-bold">
        {r.form.titleField}
        <input name="title" required maxLength={500} className={fieldClass} />
      </label>
      <label className="block text-sm font-bold">
        {r.form.url}
        <input name="url" type="url" maxLength={2000} className={fieldClass} />
      </label>
      <label className="block text-sm font-bold">
        {r.form.text}
        <textarea name="text" required minLength={20} maxLength={30000} rows={7} className={fieldClass} />
      </label>
      {error && (
        <p role="alert" className="text-sm font-bold text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy} size="lg">
        {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
        {busy ? r.form.saving : r.form.save}
      </Button>
    </form>
  );
}

/** Paste what circulates; the registry answers with the original and the word diff. */
function ComparePanel({ ws, onRecorded }: { ws: string; onRecorded: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [recorded, setRecorded] = useState(false);

  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (text.trim().length < 3) return;
    setBusy(true);
    setRecorded(false);
    try {
      setResult(await api<MatchResult>(`/workspaces/${ws}/registry/match`, { method: "POST", body: JSON.stringify({ text }) }));
    } catch (e) {
      toast.error(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function recordFake() {
    if (!result?.communique) return;
    try {
      await api(`/workspaces/${ws}/registry/${result.communique.id}/fake`, { method: "POST", body: JSON.stringify({ text }) });
      setRecorded(true);
      toast.success(r.compare.recorded);
      onRecorded();
    } catch (e) {
      toast.error(failure(e));
    }
  }

  const c = result?.communique;
  return (
    <section aria-labelledby="compare-title" className="mb-8">
      <h2 id="compare-title" className="font-display text-xl font-bold">
        {r.compare.title}
      </h2>
      <p className="mt-1 max-w-prose text-muted-foreground">{r.compare.lead}</p>
      <form onSubmit={run} className="mt-3 rounded-md border border-input bg-card focus-within:border-foreground focus-within:ring-2 focus-within:ring-foreground/15">
        <label htmlFor="compare-text" className="sr-only">
          {r.compare.label}
        </label>
        <textarea
          id="compare-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          maxLength={30000}
          placeholder={r.compare.placeholder}
          className="block w-full resize-y rounded-t-md bg-transparent p-4 text-lg leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <div className="flex justify-end border-t border-border p-2">
          <Button type="submit" variant="action" size="xl" disabled={busy || text.trim().length < 3}>
            {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
            {busy ? r.compare.running : r.compare.action}
          </Button>
        </div>
      </form>
      {result && (
        <div className="arrive mt-4 space-y-4 rounded-md border-2 border-foreground bg-card p-4" aria-live="polite">
          <RegistryDiff status={result.status} summary={result.summary} diff={result.diff} changedNumbers={result.changed_numbers} />
          {c && (
            <div className="border-t border-border pt-3">
              <p className="text-sm font-bold">{r.compare.original}</p>
              <RefLine c={c} />
              <p className="mt-0.5 font-bold">{c.title}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {c.is_demo && <Tag strong>{r.entry.demo}</Tag>}
                {c.sealed && (
                  <Tag strong>
                    <IconSealCheck className="size-3.5" aria-hidden />
                    {r.entry.sealed}
                  </Tag>
                )}
                {c.confirmed && <Tag>{r.entry.confirmed}</Tag>}
                {!c.own && c.newsroom && <Tag>{r.entry.by(c.newsroom.name)}</Tag>}
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {result.status === "modified" && c && (
              <Button onClick={recordFake} disabled={recorded}>
                {recorded ? <IconCheck aria-hidden /> : <IconPlus aria-hidden />}
                {r.compare.recordFake}
              </Button>
            )}
            {c?.seal_url && (
              <Button variant="outline" asChild>
                <a href={c.seal_url} target="_blank" rel="noreferrer">
                  <IconSealCheck aria-hidden />
                  {r.compare.openSeal}
                </a>
              </Button>
            )}
            {(result.status === "not_found" || result.status === "inconsistent") &&
              result.issuer &&
              (result.contacts?.length ? (
                result.contacts.map((p) => (
                  <Button key={p.id} variant="outline" asChild>
                    <Link href={`/w/${ws}/annuaire?q=${encodeURIComponent(p.name)}`}>
                      <IconAddressBook aria-hidden />
                      {r.compare.askContact(p.name, p.role)}
                    </Link>
                  </Button>
                ))
              ) : (
                <Button variant="outline" asChild>
                  <Link href={`/w/${ws}/annuaire?q=${encodeURIComponent(result.issuer)}`}>
                    <IconAddressBook aria-hidden />
                    {r.compare.askIssuer(result.issuer)}
                  </Link>
                </Button>
              ))}
          </div>
        </div>
      )}
    </section>
  );
}

export function RegistryView() {
  const { ws } = useParams<{ ws: string }>();
  const params = useSearchParams();
  const { joined } = useWorkspace(ws);
  const canWrite = joined;
  const isDesk = joined;
  const tabs = TABS;
  const wanted = (params.get("onglet") ?? "originaux") as Tab;
  const tab: Tab = tabs.some((x) => x.key === wanted) ? wanted : "originaux";
  const [adding, setAdding] = useState(false);

  const base = `/workspaces/${ws}/registry`;
  const query = { originaux: "?status=original", faux: "?status=fake_caught", reseau: "?scope=network&status=original", cles: "" }[tab];
  const list = useSWR<Communique[]>(tab === "cles" ? null : `${base}${query}`, fetcher);
  const originals = useSWR<Communique[]>(`${base}?status=original`, fetcher);
  const refresh = () => {
    void list.mutate();
    void originals.mutate();
  };

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 *:max-w-4xl lg:px-8 lg:pt-8">
      <header className="flex flex-wrap items-start justify-between gap-4 pb-6">
        <div className="min-w-0">
          <h1 className="page-title">{r.page.title}</h1>
          {originals.data && <p className="mt-1 text-sm text-muted-foreground">{r.page.count(originals.data.length)}</p>}
          <p className="mt-3 max-w-prose text-muted-foreground">{r.page.lead}</p>
        </div>
        {canWrite && (
          <Button size="lg" onClick={() => setAdding(!adding)} aria-expanded={adding}>
            {adding ? <IconX aria-hidden /> : <IconPlus aria-hidden />}
            {adding ? r.page.close : r.page.add}
          </Button>
        )}
      </header>
      {adding && (
        <OriginalForm
          ws={ws}
          onDone={() => {
            setAdding(false);
            refresh();
          }}
        />
      )}
      <ComparePanel ws={ws} onRecorded={refresh} />
      <nav aria-label={r.page.tabsLabel} className="mb-2 flex gap-1 overflow-x-auto border-b border-border">
        {tabs.map((x) => (
          <Link
            key={x.key}
            href={`/w/${ws}/registre${x.key === "originaux" ? "" : `?onglet=${x.key}`}`}
            aria-current={x.key === tab ? "page" : undefined}
            className={cn(
              "-mb-px shrink-0 border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors duration-150",
              x.key === tab ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {x.label}
          </Link>
        ))}
      </nav>
      {tab === "cles" ? (
        <KeysList ws={ws} />
      ) : (
        <>
          {list.error && (
            <div role="alert" className="py-6">
              <p>{r.page.loadFailed}</p>
              <Button variant="outline" className="mt-2" onClick={() => void list.mutate()}>
                {r.page.retry}
              </Button>
            </div>
          )}
          {list.data && !list.data.length && (
            <p className="py-8 text-muted-foreground">
              {tab === "faux" ? r.page.emptyFakes : tab === "reseau" ? r.page.emptyNetwork : r.page.empty}
            </p>
          )}
          <ul className="divide-y divide-border">
            {list.data?.map((c) =>
              c.status === "fake_caught" ? (
                <FakeRow key={c.id} c={c} />
              ) : (
                <OriginalRow key={c.id} c={c} ws={ws} canSeal={canWrite} canConfirm={isDesk} onChanged={refresh} />
              ),
            )}
          </ul>
        </>
      )}
    </div>
  );
}
