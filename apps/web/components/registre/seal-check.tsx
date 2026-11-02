"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { IconCircleNotch, IconQuestion, IconSealCheck, IconWarning, IconXCircle, type Icon } from "@/lib/icons";
import { registre } from "@/lib/i18n/fr/registre";
import { publicApi } from "@/lib/public-api";
import { cn } from "@/lib/utils";
import { frenchDay, type PublicSeal } from "./types";
import { Tag } from "./ui";

const c = registre.check;

type Outcome =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "failed" }
  | { state: "checked"; seal: PublicSeal; valid: boolean; where: "browser" | "server"; matchesRecord: boolean };

const bytes = (b64: string) => Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
const fromB64u = (value: string) => bytes(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4));

/** Ed25519 in the browser (WebCrypto). Null when this browser cannot, so the server checks instead. */
async function verifyHere(publicKey: string, message: string, signature: string): Promise<boolean | null> {
  try {
    if (!globalThis.crypto?.subtle) return null;
    const key = await crypto.subtle.importKey("raw", bytes(publicKey), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, fromB64u(signature), new TextEncoder().encode(message));
  } catch {
    return null;
  }
}

/** The same fingerprint as the API: Unicode NFC, runs of whitespace collapsed, SHA-256 in hex. */
async function fingerprint(text: string): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;
  const flat = text.normalize("NFC").replace(/\s+/g, " ").trim();
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(flat));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function Status({ icon: Glyph, title, lead }: { icon: Icon; title: string; lead: string }) {
  return (
    <div className="verdict-land rounded-md border-2 border-foreground bg-card p-5">
      <p className="flex items-center gap-2 font-display text-3xl font-extrabold tracking-tight">
        <Glyph className="size-8 shrink-0" aria-hidden />
        {title}
      </p>
      <p className="mt-2 max-w-prose text-lg text-pretty">{lead}</p>
    </div>
  );
}

function PasteCheck({ expected }: { expected: string }) {
  const [text, setText] = useState("");
  const [same, setSame] = useState<boolean | null>(null);
  async function run(event: React.FormEvent) {
    event.preventDefault();
    const got = await fingerprint(text);
    setSame(got === null ? null : got === expected);
  }
  if (typeof window !== "undefined" && !globalThis.crypto?.subtle) return null;
  return (
    <form onSubmit={run} className="rounded-md border border-border bg-card p-4">
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
        className="mt-2 block w-full rounded-md border border-input bg-background p-3 outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
      />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={!text.trim()}
          className="h-10 rounded-md bg-foreground px-3.5 text-sm font-bold text-background outline-none hover:bg-foreground/85 focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
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

/** /sceau/[id]: checks the issuer's signature on a communiqué, in the browser when it can. */
export function SealCheck() {
  const { id } = useParams<{ id: string }>();
  const [outcome, setOutcome] = useState<Outcome>({ state: "loading" });

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const seal = await publicApi<PublicSeal>(`/sceau/${encodeURIComponent(id)}`);
        // The signature printed in the QR travels after `#`: it never reaches a server.
        const printed = decodeURIComponent(window.location.hash.slice(1)) || seal.signature;
        let valid = await verifyHere(seal.public_key, seal.message, printed);
        let where: "browser" | "server" = "browser";
        let matchesRecord = true;
        if (valid === null) {
          const server = await publicApi<{ valid: boolean; matches_record: boolean }>(`/sceau/${encodeURIComponent(id)}/verify`, {
            method: "POST",
            body: JSON.stringify({ signature: printed }),
          });
          valid = server.valid;
          matchesRecord = server.matches_record;
          where = "server";
        }
        if (live) setOutcome({ state: "checked", seal, valid, where, matchesRecord });
      } catch (e) {
        if (live) setOutcome({ state: e instanceof ApiError && (e.status === 404 || e.status === 422) ? "missing" : "failed" });
      }
    })();
    return () => {
      live = false;
    };
  }, [id]);

  let body: React.ReactNode;
  if (outcome.state === "loading") {
    body = (
      <p role="status" className="flex items-center gap-2 text-lg">
        <IconCircleNotch className="size-5 animate-spin" aria-hidden />
        {c.loading}
      </p>
    );
  } else if (outcome.state === "missing") {
    body = <Status icon={IconQuestion} title={c.missing} lead={c.missingLead} />;
  } else if (outcome.state === "failed") {
    body = <Status icon={IconWarning} title={c.title} lead={c.failed} />;
  } else {
    const { seal, valid, where, matchesRecord } = outcome;
    // What is shown is read back from the signed message itself.
    const signed = JSON.parse(seal.message) as Record<string, string | null>;
    const revoked = seal.revoked_at;
    body = (
      <div className="space-y-6">
        {!valid ? (
          <Status icon={IconXCircle} title={c.invalid} lead={c.invalidLead} />
        ) : revoked ? (
          <Status icon={IconWarning} title={c.revoked} lead={c.revokedLead(frenchDay(revoked))} />
        ) : (
          <Status icon={IconSealCheck} title={c.valid} lead={c.validLead(signed.issuer ?? "")} />
        )}
        <div className="space-y-1 text-muted-foreground">
          <p>{where === "browser" ? c.inBrowser : c.onServer}</p>
          <p>
            {seal.sealed_by === "issuer"
              ? c.sealedByIssuer(frenchDay(seal.sealed_at))
              : c.sealedByNewsroom(seal.newsroom.name, frenchDay(seal.sealed_at))}
          </p>
          <p className="font-display text-sm font-bold tabular-nums">{c.key(seal.key_id)}</p>
        </div>
        {seal.is_demo && (
          <p className="inline-block">
            <Tag strong>{c.demo}</Tag>
          </p>
        )}
        {!matchesRecord && <p className="font-bold">{c.changed}</p>}
        <p className="max-w-prose border-y border-foreground py-3 text-lg font-bold text-pretty">{registre.seal.proves}</p>
        <section aria-labelledby="paper-title">
          <h2 id="paper-title" className="font-display text-2xl font-extrabold tracking-tight">
            {c.compare}
          </h2>
          <p className="mt-1 text-muted-foreground">{c.compareLead}</p>
          <dl className="mt-4 grid gap-x-8 gap-y-4 rounded-md border border-border bg-card p-4 sm:grid-cols-2">
            {(
              [
                [c.issuer, signed.issuer],
                [c.number, signed.number ? `N° ${signed.number}` : "—"],
                [c.date, signed.issued_on ? frenchDay(signed.issued_on) : "—"],
                [c.titleField, signed.title],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className={cn(label === c.titleField && "sm:col-span-2")}>
                <dt className="text-sm text-muted-foreground">{label}</dt>
                <dd className="font-display text-xl font-bold text-pretty tabular-nums">{value}</dd>
              </div>
            ))}
            <div className="sm:col-span-2">
              <dt className="text-sm text-muted-foreground">{c.fingerprint}</dt>
              <dd className="font-mono text-xs break-all">{signed.fingerprint}</dd>
            </div>
          </dl>
        </section>
        <details className="rounded-md border border-border bg-card p-4">
          <summary className="cursor-pointer font-bold">{c.text}</summary>
          <p className="mt-3 max-w-prose whitespace-pre-wrap">{seal.text}</p>
          <p className="mt-2 text-sm text-muted-foreground">{c.newsroom(seal.newsroom.name)}</p>
        </details>
        {signed.fingerprint && <PasteCheck expected={signed.fingerprint} />}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-20 lg:px-10 lg:pt-14">
      <h1 className="page-title">{c.title}</h1>
      <div className="mt-8" aria-live="polite">
        {body}
      </div>
      <p className="mt-10">
        <Link href="/officiel" className="font-bold underline underline-offset-4">
          {c.feed}
        </Link>
      </p>
    </div>
  );
}
