"use client";

import { Em, Lines } from "@/components/site/public/kit";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { SealStatus, SignedFields } from "@/components/seal/seal-result";
import { useSealCheck } from "@/components/seal/use-seal-check";
import { useDay, useMoment, useT } from "@/lib/i18n";
import { IconCircleNotch, IconQuestion, IconSealCheck, IconWarning, IconWifiSlash, type Icon } from "@/lib/icons";
import { useOnline } from "@/lib/offline";
import { Tag } from "./ui";

/** The same fingerprint as the API: Unicode NFC, runs of whitespace collapsed, SHA-256 in hex. */
async function fingerprint(text: string): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;
  const flat = text.normalize("NFC").replace(/\s+/g, " ").trim();
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(flat));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function Status({ icon: Glyph, title, lead }: { icon: Icon; title: string; lead: string }) {
  return (
    <div className="verdict-land rounded-[24px] border-2 border-foreground bg-card p-6 md:p-7">
      <p className="flex items-center gap-2 font-display text-3xl font-extrabold tracking-tight">
        <Glyph className="size-8 shrink-0" aria-hidden />
        {title}
      </p>
      <p className="mt-2 max-w-prose text-lg text-pretty">{lead}</p>
    </div>
  );
}

function PasteCheck({ expected }: { expected: string }) {
  const c = useT().registre.check;
  const [text, setText] = useState("");
  const [same, setSame] = useState<boolean | null>(null);
  async function run(event: React.FormEvent) {
    event.preventDefault();
    const got = await fingerprint(text);
    setSame(got === null ? null : got === expected);
  }
  if (typeof window !== "undefined" && !globalThis.crypto?.subtle) return null;
  return (
    <form onSubmit={run} className="rounded-[24px] border border-border bg-card p-5 md:p-6">
      <label htmlFor="paste" className="font-bold">
        {c.paste}
      </label>
      <textarea
        id="paste"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setSame(null);
        }}
        rows={4}
        placeholder={c.pastePlaceholder}
        aria-label={c.pasteLabel}
        className="mt-3 block w-full rounded-[20px] border border-input bg-background px-5 py-3.5 outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
      />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={!text.trim()}
          className="h-11 rounded-full bg-primary px-5 text-sm font-bold text-primary-foreground outline-none hover:bg-primary-hover hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:bg-raised disabled:text-muted-foreground"
        >
          {c.pasteAction}
        </button>
        {same !== null && (
          <p role="status" className="flex items-center gap-1.5 font-bold">
            {same ? <IconSealCheck className="size-5" aria-hidden /> : <IconWarning className="size-5" aria-hidden />}
            {same ? c.same : c.different}
          </p>
        )}
      </div>
    </form>
  );
}

/** The page's own address, fragment included (known only in the browser; null on the server). */
function useHref(): string | null {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener("hashchange", onChange);
      return () => window.removeEventListener("hashchange", onChange);
    },
    () => window.location.href,
    () => null,
  );
}

/** /seal/[id]: checks the issuer's signature on a communiqué from the QR alone, on this device and
 *  with no network (the issuers' keys are kept here); online, also against the registry. The id is
 *  read from the address, not the route: offline the page may come from the service worker's copy. */
export function SealCheck() {
  const t = useT();
  const c = t.registre.check;
  const s = t.offline.seal;
  const moment = useMoment();
  const day = useDay();
  const online = useOnline();
  const outcome = useSealCheck(useHref());

  let body: React.ReactNode;
  if (outcome.phase === "checking") {
    body = (
      <p role="status" className="flex items-center gap-2 text-lg">
        <IconCircleNotch className="size-5 animate-spin" aria-hidden />
        {c.loading}
      </p>
    );
  } else if (outcome.phase === "none") {
    body = <Status icon={IconQuestion} title={c.missing} lead={c.missingLead} />;
  } else if (outcome.phase === "needs_network") {
    body = <Status icon={IconWifiSlash} title={t.offline.banner.off} lead={s.oldQr} />;
  } else if (outcome.phase === "failed") {
    body = <Status icon={IconWarning} title={c.title} lead={c.failed} />;
  } else {
    const { check, where, keysAt, keysFresh, record, seal } = outcome;
    const signed = check.payload ?? {};
    body = (
      <div className="space-y-6">
        <SealStatus check={check} />
        <div className="space-y-1 text-muted-foreground">
          <p>{where === "server" ? c.onServer : keysFresh || !keysAt ? s.offlineNoteFresh : s.offlineNote(moment(keysAt))}</p>
          {record ? <p className="font-bold text-foreground">{record.same ? s.recordSame : c.changed}</p> : !online && <p>{s.recordLater}</p>}
          {seal && (
            <p>{seal.sealed_by === "issuer" ? c.sealedByIssuer(day(seal.sealed_at)) : c.sealedByNewsroom(seal.newsroom.name, day(seal.sealed_at))}</p>
          )}
          <p className="font-display text-sm font-bold tabular-nums">{c.key(outcome.parsed.form === "full" ? outcome.parsed.keyId : "")}</p>
        </div>
        {seal?.is_demo && (
          <p className="inline-block">
            <Tag strong>{c.demo}</Tag>
          </p>
        )}
        <p className="max-w-prose border-y border-foreground py-3 text-lg font-bold text-pretty">{t.registre.seal.proves}</p>
        <section aria-labelledby="paper-title">
          <h2 id="paper-title" className="font-display text-2xl font-extrabold tracking-tight">
            {c.compare}
          </h2>
          <p className="mt-1 mb-4 text-muted-foreground">{c.compareLead}</p>
          <SignedFields check={check} />
        </section>
        {seal && (
          <details className="rounded-[20px] border border-border bg-card p-5">
            <summary className="cursor-pointer font-bold">{c.text}</summary>
            <p className="mt-3 max-w-prose whitespace-pre-wrap">{seal.text}</p>
            <p className="mt-2 text-sm text-muted-foreground">{c.newsroom(seal.newsroom.name)}</p>
          </details>
        )}
        {typeof signed.fingerprint === "string" && <PasteCheck expected={signed.fingerprint} />}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-24 lg:px-10 lg:pt-16">
      <Lines className="pub-display" lines={t.look.seal.hero.map((line, i) => <Em key={i} text={line} />)} />
      <div className="rise mt-10" style={{ "--d": "0.25s" } as React.CSSProperties} aria-live="polite">
        {body}
      </div>
      <p className="mt-10 flex flex-wrap gap-3">
        <Link href="/scanner" className="pub-ghost-btn">
          {t.offline.scanner.again}
        </Link>
        <Link href="/official" className="pub-ghost-btn">
          {c.feed}
        </Link>
      </p>
    </div>
  );
}
