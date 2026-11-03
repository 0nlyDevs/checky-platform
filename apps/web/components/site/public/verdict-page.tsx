"use client";

import { EcoGate } from "@/components/prefs/eco";
import { VerifiedBadge } from "@/components/verification/status";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { StepLine } from "@/components/flow/step-line";
import { Evidence, ShareActions, type SignedVerdict, Trajet, VerdictBlock } from "@/components/site/public/public-verdict";
import { useDay, useT } from "@/lib/i18n";
import { IconArrowLeft, IconArrowRight, IconQuestion, IconSealCheck, IconSpeakerHigh, IconWarning, IconXCircle } from "@/lib/icons";
import { SealStatus, SignedFields } from "@/components/seal/seal-result";
import { type SealOutcome, useSealCheck } from "@/components/seal/use-seal-check";
import { publicApi } from "@/lib/public-api";
import { tidy } from "@/lib/typo";

/** One published verdict, at its own shareable address: the answer first, why, the evidence with
 *  its dates, where the correction went, then share. */
export function VerdictPage() {
  const params = useParams<{ id: string }>();
  // Offline this page may be the service worker's copy of another verdict's page: the address says which.
  const href = usePageHref();
  const id = (href && new URL(href).pathname.split("/").filter(Boolean)[1]) || params.id;
  const t = useT();
  const p = t.site.pub.file;
  const day = useDay();
  const [v, setV] = useState<(SignedVerdict & { voice_note?: VoiceNote | null }) | null | "missing">(null);
  const sealed = useSealCheck(href && new URL(href).hash ? href : null);

  useEffect(() => {
    if (!href) return;
    publicApi<SignedVerdict>(`/verdicts/${id}`).then(setV).catch(() => setV("missing"));
  }, [id, href]);

  if (v === "missing" && sealed.phase === "done")
    return (
      <Shell>
        <p className="mt-8 max-w-[70ch] text-lg text-pretty">{t.offline.seal.offlineVerdict}</p>
        <h1 className="mt-4 font-display text-2xl font-extrabold tracking-tight">{t.offline.seal.verdictTitle}</h1>
        <SealStatus check={sealed.check} className="mt-4" />
        <div className="mt-6">
          <SignedFields check={sealed.check} />
        </div>
      </Shell>
    );
  if (v === "missing")
    return (
      <Shell>
        <p className="mt-8 text-xl">{p.notFound}</p>
      </Shell>
    );
  if (!v)
    return (
      <Shell>
        <div className="mt-10 h-14 w-2/3 rounded-[20px] bg-muted" />
        <div className="mt-8 h-56 rounded-[24px] bg-muted" />
      </Shell>
    );

  const origin = v.origin ? ((t.origins as Record<string, string>)[v.origin] ?? null) : null;
  return (
    <Shell>
      <h1 className="pub-title rise mt-8 max-w-[26ch] text-pretty md:mt-10">«&nbsp;{tidy(v.title)}&nbsp;»</h1>
      <p className="rise mt-4 text-muted-foreground" style={{ "--d": "0.15s" } as React.CSSProperties}>
        {t.publicLayer.check.signed.by(v.newsroom.name, day(v.signed_at ?? v.published_at))}
        {checkNumber(v.ref) !== null ? <span className="tabular"> · {p.number(checkNumber(v.ref)!)}</span> : v.ref && <span className="tabular"> · {v.ref}</span>}
      </p>
      <VerifiedBadge className="mt-1" />
      <CardSeal outcome={sealed} newsroom={v.newsroom.name} />

      <div className="mt-8 grid gap-12 md:mt-10 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <VerdictBlock v={v} />
          <div className="mt-5">
            <ShareActions v={v} primary />
          </div>
          {v.voice_note && <NewsroomVoice note={v.voice_note} />}

          {(v.confidence || !!v.evidence?.length) && (
            <section className="mt-10">
              <Evidence v={v} />
            </section>
          )}

          {v.post && (
            <section className="mt-10">
              <h2 className="font-display text-lg font-bold">{p.post}</h2>
              <p className="mt-2 max-w-[70ch] text-lg leading-relaxed text-pretty">{v.post}</p>
            </section>
          )}

          {/* Older verdicts have only source titles: listed as before. */}
          {!v.evidence?.length && (
            <section className="mt-10">
              <h2 className="font-display text-lg font-bold">{p.sources}</h2>
              {v.sources.length ? (
                <ol className="mt-2 border-t border-foreground">
                  {v.sources.map((s, i) => (
                    <li key={s} className="arrive flex gap-4 border-b border-border py-3" style={{ "--i": i } as React.CSSProperties}>
                      <span className="font-display font-bold text-muted-foreground tabular">{String(i + 1).padStart(2, "0")}</span>
                      <span className="min-w-0 text-pretty">{s}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-muted-foreground">{p.noSources}</p>
              )}
            </section>
          )}

          <Trajet id={v.id} className="mt-10" />
        </div>

        <aside className="lg:border-l lg:border-border lg:pl-8">
          <h2 className="sr-only">{t.flow.label}</h2>
          <StepLine
            states={{ claim: "done", evidence: "done", conclusion: "done" }}
            notes={{
              claim: v.first_seen_at ? p.seenOn(day(v.first_seen_at), origin) : undefined,
              evidence: v.sources.length ? p.sourcesSeen(v.sources.length) : p.noSources,
              conclusion: p.publishedBy(day(v.published_at), v.newsroom.name),
            }}
          />
          <div className="mt-8 rounded-[20px] border border-border bg-card p-5">
            <p className="text-pretty">{p.wrong}</p>
            <Link
              href={`/signaler?texte=${encodeURIComponent(v.title)}`}
              className="mt-2 inline-flex items-center gap-1.5 font-bold underline underline-offset-4"
            >
              {p.wrongAction} <IconArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </aside>
      </div>
    </Shell>
  );
}

type VoiceNote = { url: string; mime: string; seconds: number | null; language: string };

/** « vérification 145 » from FAN-0145: the number said on air, typed in an SMS, printed on the card. */
function checkNumber(ref: string | null | undefined): number | null {
  const m = /(\d{1,8})$/.exec(ref ?? "");
  return m ? Number(m[1]) : null;
}

/** « Écouter la rédaction »: the journalist's own voice note (never a machine voice, never a
 *  transcript). In Mode éco it waits for a tap. */
function NewsroomVoice({ note }: { note: VoiceNote }) {
  const p = useT().site.pub.file;
  return (
    <section className="mt-6 max-w-xl rounded-[20px] border border-border bg-card p-5" aria-labelledby="newsroom-voice">
      <h2 id="newsroom-voice" className="flex items-center gap-2 font-display text-lg font-bold">
        <IconSpeakerHigh className="size-5" aria-hidden />
        {p.newsroomVoice}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{p.newsroomVoiceLead(note.seconds ? Math.round(note.seconds) : null)}</p>
      <EcoGate kind="audio" className="mt-3">
        <audio controls preload="none" src={note.url} className="mt-3 w-full" aria-label={p.newsroomVoice} lang={note.language}>
          <track kind="captions" />
        </audio>
      </EcoGate>
    </section>
  );
}

/** The page's address with its fragment, known only in the browser. */
function usePageHref(): string | null {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener("hashchange", onChange);
      return () => window.removeEventListener("hashchange", onChange);
    },
    () => window.location.href,
    () => null,
  );
}

/** The QR of a printed card carries the newsroom's seal after `#` (message.signature.key_id). The
 *  fragment never reaches a server by itself: it is checked on this device with the kept keys (no
 *  network needed), then, online, against this verdict, and the page says in one line whether the
 *  card in hand is genuine and current. Nothing without a seal. */
function CardSeal({ outcome, newsroom }: { outcome: SealOutcome; newsroom: string }) {
  const t = useT();
  const s = t.site.pub.file.seal;
  if (outcome.phase !== "done") return null;
  const { check, record } = outcome;
  const [Glyph, text] =
    check.status === "revoked"
      ? [IconWarning, s.revoked]
      : check.status === "mismatch" || (record && !record.same)
        ? [IconXCircle, s.invalid]
        : check.status === "authentic"
          ? record && record.current === false
            ? [IconWarning, s.old]
            : [IconSealCheck, s.valid(newsroom)]
          : [IconQuestion, t.offline.seal.unknownLead];
  return (
    <p role="status" data-seal={check.status} className="mt-4 flex max-w-[70ch] items-start gap-2 rounded-[20px] border border-foreground bg-card px-4 py-3 font-bold text-pretty">
      <Glyph className="mt-0.5 size-5 shrink-0" aria-hidden />
      {text}
    </p>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const p = useT().site.pub.file;
  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-8 pb-24 lg:px-10 lg:pt-10">
      <Link
        href="/verifies"
        className="group inline-flex h-10 items-center gap-2 rounded-full border border-border bg-card px-4 text-sm font-bold text-foreground outline-none hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <IconArrowLeft className="size-4 transition-transform duration-300 group-hover:-translate-x-0.5" aria-hidden /> {p.back}
      </Link>
      {children}
    </div>
  );
}
