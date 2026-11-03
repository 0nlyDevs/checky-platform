"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { SealStatus, SignedFields } from "@/components/seal/seal-result";
import { useSealCheck } from "@/components/seal/use-seal-check";
import { CheckForm } from "@/components/site/public/check";
import { Em, Lines } from "@/components/site/public/kit";
import { Button } from "@/components/ui/button";
import { useMoment, useT } from "@/lib/i18n";
import { IconArrowRight, IconCamera, IconCircleNotch, IconImage, IconNewspaper, IconStop, IconWarning } from "@/lib/icons";
import { isOffline } from "@/lib/offline";
import { addToOutbox } from "@/lib/outbox";
import { parseSeal } from "@/lib/seal";
import { readQr, readText, sendPhoto } from "./read-image";

/** The seal read from a QR, checked here and now (no network needed), with what to compare. */
function ScanResult({ url, onAgain }: { url: string; onAgain: () => void }) {
  const t = useT();
  const s = t.offline.seal;
  const sc = t.offline.scanner;
  const moment = useMoment();
  const outcome = useSealCheck(url);
  // Opened here, not on the printed domain: offline, this device's copy of the page answers.
  const at = new URL(url, window.location.origin);
  const local = `${at.pathname}${at.hash}`;
  return (
    <section aria-live="polite" className="space-y-5">
      {outcome.phase === "checking" && (
        <p role="status" className="flex items-center gap-2 text-lg">
          <IconCircleNotch className="size-5 animate-spin" aria-hidden /> {t.registre.check.loading}
        </p>
      )}
      {outcome.phase === "needs_network" && <p className="text-lg font-bold">{s.oldQr}</p>}
      {(outcome.phase === "none" || outcome.phase === "failed") && <p className="text-lg font-bold">{t.registre.check.missingLead}</p>}
      {outcome.phase === "done" && (
        <>
          <SealStatus check={outcome.check} />
          <p className="text-muted-foreground">
            {outcome.where === "server" ? t.registre.check.onServer : outcome.keysFresh || !outcome.keysAt ? s.offlineNoteFresh : s.offlineNote(moment(outcome.keysAt))}
            {outcome.record ? ` ${outcome.record.same ? s.recordSame : t.registre.check.changed}` : ""}
          </p>
          <SignedFields check={outcome.check} />
        </>
      )}
      <div className="flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <a href={local}>
            {sc.open} <IconArrowRight aria-hidden />
          </a>
        </Button>
        <Button type="button" variant="ghost" onClick={onAgain}>
          {sc.again}
        </Button>
      </div>
    </section>
  );
}

/** The camera, reading QR codes frame after frame until one is found. */
function Camera({ onCode, onDenied }: { onCode: (text: string) => void; onDenied: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const sc = useT().offline.scanner;
  useEffect(() => {
    let stream: MediaStream | null = null;
    let stopped = false;
    let timer = 0;
    const scratch = document.createElement("canvas");
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      } catch {
        return onDenied();
      }
      if (stopped || !video.current) return stream.getTracks().forEach((tr) => tr.stop());
      video.current.srcObject = stream;
      await video.current.play().catch(() => null);
      const tick = async () => {
        if (stopped || !video.current) return;
        const code = await readQr(video.current, scratch).catch(() => null);
        if (code && !stopped) return onCode(code);
        timer = window.setTimeout(tick, 250);
      };
      void tick();
    })();
    return () => {
      stopped = true;
      clearTimeout(timer);
      stream?.getTracks().forEach((tr) => tr.stop());
    };
  }, [onCode, onDenied]);
  return (
    <div className="scan-finder">
      <video ref={video} muted playsInline className="aspect-[4/3] w-full object-cover" aria-label={sc.aiming} />
      <span className="scan-target" aria-hidden>
        <i />
        <i />
        <i />
        <i />
      </span>
      <span className="scan-line" aria-hidden />
      <p className="scan-cap">{sc.aiming}</p>
    </div>
  );
}

const bitmapOf = (file: Blob) => createImageBitmap(file).catch(() => null);

/**
 * « Scanner »: the camera reads a seal's QR and checks it on the phone, with no network; a photo of
 * a printed communiqué or newspaper page goes to the existing check (the desk's Vérifier when `ws`
 * is given, the public check otherwise). Its text is read on the device where the browser can;
 * otherwise the desk sends the photo (kept in « À envoyer » while offline) and the public page asks
 * for its first lines.
 */
export function ScannerView({ ws }: { ws?: string }) {
  const t = useT();
  const sc = t.offline.scanner;
  const router = useRouter();
  const [camera, setCamera] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pageText, setPageText] = useState<{ text: string; read: boolean } | null>(null);
  const [onCode] = useState(() => (text: string) => {
    setCamera(false);
    setCode(text);
  });
  const [onDenied] = useState(() => () => {
    setCamera(false);
    setNote(t.offline.scanner.denied);
  });

  const isSeal = code ? parseSeal(code, window.location.origin) !== null : false;

  async function qrPhoto(file: File | undefined) {
    if (!file) return;
    setNote(null);
    setCode(null);
    const picture = await bitmapOf(file);
    const text = picture ? await readQr(picture) : null;
    if (text) setCode(text);
    else setNote(sc.noQr);
  }

  async function pagePhoto(file: File | undefined) {
    if (!file) return;
    setNote(null);
    setCode(null);
    setBusy(sc.reading);
    const picture = await bitmapOf(file);
    // A QR on the page is the strongest answer: checked first.
    const qr = picture ? await readQr(picture) : null;
    if (qr && parseSeal(qr, window.location.origin)) {
      setBusy(null);
      return setCode(qr);
    }
    const text = picture ? await readText(picture) : null;
    setBusy(null);
    if (ws) {
      if (text) return router.push(`/w/${ws}/verify?lien=${encodeURIComponent(text.slice(0, 6000))}` as never);
      if (isOffline()) {
        await addToOutbox({ ws, photo: file, name: file.name });
        return setNote(sc.queued);
      }
      setBusy(sc.sending);
      try {
        const source = await sendPhoto(ws, file, file.name);
        setNote(sc.sent);
        router.push(`/w/${ws}/verify?source=${source}` as never);
      } catch {
        setNote(sc.failed);
      } finally {
        setBusy(null);
      }
      return;
    }
    setPageText({ text: text ?? "", read: Boolean(text) });
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-24 lg:px-10 lg:pt-16">
      <Lines className="pub-display" lines={t.look.scanner.hero.map((line, i) => <Em key={i} text={line} />)} />
      <p className="pub-lead rise mt-7 max-w-[62ch]" style={{ "--d": "0.25s" } as React.CSSProperties}>
        {sc.lead}
      </p>

      <div className="mt-8 space-y-6">
        {code ? (
          isSeal ? (
            <ScanResult url={code} onAgain={() => setCode(null)} />
          ) : (
            <div className="space-y-3 rounded-[24px] border border-border bg-card p-5">
              <p className="flex items-center gap-2 font-bold">
                <IconWarning className="size-5" aria-hidden /> {sc.notSeal}
              </p>
              <p className="text-sm text-muted-foreground">{sc.link}</p>
              <p className="font-mono text-sm break-all">{code}</p>
              <Button type="button" variant="ghost" onClick={() => setCode(null)}>
                {sc.again}
              </Button>
            </div>
          )
        ) : camera ? (
          <>
            <Camera onCode={onCode} onDenied={onDenied} />
            <Button type="button" variant="outline" size="xl" className="rounded-full px-6" onClick={() => setCamera(false)}>
              <IconStop aria-hidden /> {sc.stop}
            </Button>
          </>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Button type="button" size="xl" variant="action" className="rounded-full px-6" onClick={() => setCamera(true)}>
              <IconCamera aria-hidden /> {sc.start}
            </Button>
            <Button asChild type="button" size="xl" variant="outline" className="rounded-full px-6 has-focus-visible:ring-2 has-focus-visible:ring-ring">
              <label className="cursor-pointer">
                <IconImage aria-hidden /> {sc.pickQr}
                <input type="file" accept="image/*" className="sr-only" data-scan="qr" onChange={(e) => void qrPhoto(e.target.files?.[0])} />
              </label>
            </Button>
          </div>
        )}

        {note && (
          <p role="status" className="font-bold text-pretty">
            {note}
          </p>
        )}

        <section aria-labelledby="page-photo" className="rounded-[24px] border border-border bg-card p-5 md:p-6">
          <h2 id="page-photo" className="flex items-center gap-2 font-display text-xl font-bold">
            <IconNewspaper className="size-5" aria-hidden /> {sc.pageTitle}
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button asChild variant="outline" size="xl" className="rounded-full px-6 has-focus-visible:ring-2 has-focus-visible:ring-ring" disabled={Boolean(busy)}>
              <label className="cursor-pointer">
                <IconCamera aria-hidden /> {sc.pickPage}
                <input type="file" accept="image/*" capture="environment" className="sr-only" data-scan="page" onChange={(e) => void pagePhoto(e.target.files?.[0])} />
              </label>
            </Button>
            {busy && (
              <span role="status" className="inline-flex items-center gap-2 text-sm">
                <IconCircleNotch className="size-4 animate-spin" aria-hidden /> {busy}
              </span>
            )}
          </div>
          {pageText && (
            <div className="mt-4">
              <p className="mb-2 text-sm text-pretty text-muted-foreground">{pageText.read ? sc.readText : sc.noReader}</p>
              <CheckForm id="scan" initialText={pageText.text} key={pageText.text} />
            </div>
          )}
        </section>

        {ws && (
          <p>
            <Link href={`/w/${ws}/verify`} className="font-bold underline underline-offset-4">
              {t.nav.check}
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
