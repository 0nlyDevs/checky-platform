"use client";

import type { Item, Me, Verdict } from "@fanilo/shared";
import { toPng } from "html-to-image";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { IconCheck, IconCircleNotch, IconCopy, IconDownloadSimple, IconSparkle } from "@/lib/icons";
import { toast } from "sonner";
import { LogoMark } from "@/components/brand/logo";
import { VERDICT_META } from "@/components/claims/verdict";
import { readResearch, type DiffPart } from "@/components/dossier/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, ApiError, fetcher } from "@/lib/api";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";
import type { Source } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Lang = "fr" | "mg";
/** The square card, the 9:16 story, and for a doctored communiqué the fake above the original. */
export type CardFormat = "square" | "story" | "communique";

// The card is a shared artefact: fixed palette from DESIGN.md, the same in light and dark mode.
const C = { band: "#0a0a0b", ground: "#f3f2ee", ink: "#0a0a0b", muted: "#55544e", rule: "#dcdbd5" };
const FILL: Record<Verdict, { fill: string; on: string }> = {
  true: { fill: "#0b6b3a", on: "#ffffff" },
  misleading: { fill: "#8a5700", on: "#ffffff" },
  false: { fill: "#b3231a", on: "#ffffff" },
  unverifiable: { fill: "#1d58c4", on: "#ffffff" },
};
// The diff's red: a soft ground and a dark red ink (contrast ≥ 4.5:1 on each other).
const RED = { soft: "#fbe4e1", ink: "#8f1c14" };

/** CSS size of each format; exported at 2× (1080 × 1080, 1080 × 1920). */
const SIZE: Record<CardFormat, { w: number; h: number }> = {
  square: { w: 540, h: 540 },
  communique: { w: 540, h: 540 },
  story: { w: 540, h: 960 },
};

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** The verdict's seal as the API gives it: the QR's URL (the public page + the signed fragment). */
type Seal = { url: string; number: number | null };

/** `checky.mg/v/145`, the short address of the verification number, on the seal's own origin. */
function shortLink(seal: Seal | null | undefined): string | null {
  if (!seal || seal.number == null) return null;
  try {
    return `${new URL(seal.url).host}/v/${seal.number}`;
  } catch {
    return null;
  }
}

/** The QR as a data URL drawn in the browser (nothing leaves the page to draw it). */
function useQr(url: string | null | undefined, width: number) {
  const [qr, setQr] = useState<{ url: string; png: string } | null>(null);
  useEffect(() => {
    if (!url) return;
    let live = true;
    // Level L keeps the long sealed URL at the fewest modules, so a small QR stays readable.
    QRCode.toDataURL(url, { margin: 1, width: width * 4, errorCorrectionLevel: "L", color: { dark: "#0a0a0bff", light: "#ffffffff" } })
      .then((png) => live && setQr({ url, png }))
      .catch(() => live && setQr(null));
    return () => {
      live = false;
    };
  }, [url, width]);
  return url && qr?.url === url ? qr.png : null;
}

function SealQr({ seal, size, lang, png }: { seal: Seal | null; size: number; lang: Lang; png: string | null }) {
  if (!seal) return null;
  return (
    <div style={{ width: size, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      {png ? (
        // A data URL drawn here: next/image has nothing to optimise.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={png} alt={t.card.qrAlt} width={size} height={size} style={{ width: size, height: size, display: "block", imageRendering: "pixelated" }} data-seal-qr={seal.url} />
      ) : (
        <span style={{ width: size, height: size, background: "#ffffff", display: "block" }} aria-hidden />
      )}
      <span style={{ color: C.ink, fontSize: 11, lineHeight: 1.2, textAlign: "center" }}>{t.card.words[lang].scan}</span>
    </div>
  );
}

function VerdictPill({ verdict, lang, big }: { verdict: Verdict; lang: Lang; big?: boolean }) {
  const Icon = VERDICT_META[verdict].icon;
  return (
    <div
      style={{
        background: FILL[verdict].fill,
        color: FILL[verdict].on,
        borderRadius: 4,
        padding: big ? "16px 22px" : "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        alignSelf: "flex-start",
        flexShrink: 0,
      }}
    >
      <Icon className={big ? "size-11" : "size-8"} aria-hidden />
      <span className={cn("font-display leading-none font-extrabold tracking-tight", big ? "text-6xl" : "text-4xl")}>{t.card.words[lang].verdicts[verdict]}</span>
    </div>
  );
}

function Band({ lang, label }: { lang: Lang; label?: string }) {
  return (
    <div style={{ background: C.band, color: "#f3f2ee", padding: "18px 28px", display: "flex", alignItems: "center", gap: 10 }}>
      <LogoMark className="size-6" />
      <span className="font-display text-xl font-extrabold">{brand.name}</span>
      <span style={{ marginLeft: "auto", opacity: 0.85 }} className="text-sm">
        {label ?? t.card.words[lang].checked}
      </span>
    </div>
  );
}

/** Who signed, the number and its short link: the same « vérification 145 » on every format. */
function Byline({ lang, desk, verified, seal, refLabel }: { lang: Lang; desk: string; verified: boolean; seal: Seal | null; refLabel: string | null }) {
  const words = t.card.words[lang];
  const label = seal?.number != null ? words.number(seal.number) : refLabel;
  const short = shortLink(seal);
  return (
    <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 3, color: C.muted }} className="text-sm">
      {label && (
        <span className="font-display text-lg leading-tight font-bold tabular" style={{ color: C.ink }} data-check-label>
          {label}
        </span>
      )}
      {short && (
        <span className="font-bold" style={{ color: C.ink }}>
          {short}
        </span>
      )}
      <span className="truncate">{words.by(desk)}</span>
      {verified && (
        <span className="font-bold" style={{ color: C.ink }}>
          ✓ {words.verified}
        </span>
      )}
    </div>
  );
}

type CardProps = { item: Item; verdict: Verdict; reason: string; sources: Source[]; lang: Lang; desk: string; verified: boolean; seal: Seal | null; qr: string | null };

function sourceNames(sources: Source[]) {
  return sources
    .map((s) => (s.url ? host(s.url) : s.title))
    .filter((v, i, a) => a.indexOf(v) === i)
    .slice(0, 3);
}

const clamp = (lines: number): React.CSSProperties => ({ display: "-webkit-box", WebkitLineClamp: lines, WebkitBoxOrient: "vertical", overflow: "hidden" });

/** 540 × 540 CSS pixels, exported at 2× = 1080 × 1080, the size Facebook and WhatsApp show square. */
function SquareCard({ item, verdict, reason, sources, lang, desk, verified, seal, qr }: CardProps) {
  const words = t.card.words[lang];
  const names = sourceNames(sources);
  const ref = (item.data as { ref?: string }).ref ?? null;
  return (
    <div style={{ width: 540, height: 540, background: C.ground, color: C.ink, display: "flex", flexDirection: "column" }} className="font-sans">
      <Band lang={lang} />
      <div style={{ padding: "18px 28px 10px", flex: 1, minHeight: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: 12 }}>
        <VerdictPill verdict={verdict} lang={lang} />
        <div>
          <p style={{ color: C.muted }} className="text-sm">
            {words.claim}
          </p>
          <p className="quote mt-0.5 text-xl leading-snug text-pretty" style={clamp(3)}>
            « {item.title} »
          </p>
        </div>
        {reason && (
          <p className="text-base leading-snug text-pretty" style={clamp(seal ? 3 : 4)}>
            {reason}
          </p>
        )}
        {names.length > 0 && (
          <p style={{ color: C.muted }} className="truncate text-sm">
            {words.sources} : {names.join(" · ")}
          </p>
        )}
      </div>
      <div
        style={{ borderTop: `1px solid ${C.rule}`, margin: "0 28px", padding: "10px 0 14px", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}
      >
        <Byline lang={lang} desk={desk} verified={verified} seal={seal} refLabel={ref} />
        <SealQr seal={seal} size={124} lang={lang} png={qr} />
      </div>
    </div>
  );
}

/** 540 × 960 CSS pixels = 1080 × 1920, the WhatsApp and Facebook story. The top and bottom bands
 *  sit under the apps' own bars: nothing that matters is placed there. */
function StoryCard({ item, verdict, reason, sources, lang, desk, verified, seal, qr }: CardProps) {
  const words = t.card.words[lang];
  const names = sourceNames(sources);
  const ref = (item.data as { ref?: string }).ref ?? null;
  return (
    <div style={{ width: 540, height: 960, background: C.ground, color: C.ink, display: "flex", flexDirection: "column" }} className="font-sans">
      <div style={{ height: 64, background: C.band, flexShrink: 0 }} aria-hidden />
      <Band lang={lang} />
      <div style={{ padding: "32px 36px 20px", flex: 1, minHeight: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: 26 }}>
        <VerdictPill verdict={verdict} lang={lang} big />
        <div>
          <p style={{ color: C.muted }} className="text-base">
            {words.claim}
          </p>
          <p className="quote mt-1 text-3xl leading-snug text-pretty" style={clamp(5)}>
            « {item.title} »
          </p>
        </div>
        {reason && (
          <p className="text-xl leading-relaxed text-pretty" style={clamp(6)}>
            {reason}
          </p>
        )}
        {names.length > 0 && (
          <p style={{ color: C.muted }} className="text-base">
            {words.sources} : {names.join(" · ")}
          </p>
        )}
      </div>
      <div
        style={{ borderTop: `1px solid ${C.rule}`, margin: "0 36px", padding: "18px 0 22px", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 20 }}
      >
        <Byline lang={lang} desk={desk} verified={verified} seal={seal} refLabel={ref} />
        <SealQr seal={seal} size={176} lang={lang} png={qr} />
      </div>
      <div style={{ height: 64, flexShrink: 0 }} aria-hidden />
    </div>
  );
}

type Part = { text: string; changed: boolean };

/** Each side of the registry's word diff (`a` the original, `b` the copy), long identical runs
 *  folded to « … » so the changed words fit on a card. */
export function diffSides(diff: DiffPart[], keep = 6): { fake: Part[]; original: Part[] } {
  const fake: Part[] = [];
  const original: Part[] = [];
  diff.forEach((d, i) => {
    if (d.op === "equal") {
      const w = d.a.split(" ").filter(Boolean);
      const head = i === 0 ? 0 : keep;
      const tail = i === diff.length - 1 ? 0 : keep;
      const text =
        w.length <= head + tail + 2
          ? w.join(" ")
          : [w.slice(0, head).join(" "), "…", w.slice(w.length - tail).join(" ")].filter(Boolean).join(" ");
      if (text) {
        fake.push({ text, changed: false });
        original.push({ text, changed: false });
      }
      return;
    }
    if (d.b) fake.push({ text: d.b, changed: true });
    if (d.a) original.push({ text: d.a, changed: true });
  });
  return { fake, original };
}

function Words({ parts, mark }: { parts: Part[]; mark: (text: string, key: number) => React.ReactNode }) {
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && " "}
          {p.changed ? mark(p.text, i) : p.text}
        </span>
      ))}
    </>
  );
}

type Registry = { issuer: string | null; number: string | null; diff: DiffPart[] };

/** « Ce communiqué est falsifié — voici l'original »: what circulates, its changed words struck
 *  through on red, above the registered original with those words in bold. Never red alone: the
 *  struck words and the labels say it too. */
function CommuniqueCard({ item, verdict, lang, desk, verified, seal, qr, registry }: CardProps & { registry: Registry }) {
  const words = t.card.words[lang];
  const { fake, original } = diffSides(registry.diff);
  const ref = (item.data as { ref?: string }).ref ?? null;
  const who = [registry.issuer, registry.number ? `n° ${registry.number}` : null].filter(Boolean).join(" · ");
  return (
    <div style={{ width: 540, height: 540, background: C.ground, color: C.ink, display: "flex", flexDirection: "column" }} className="font-sans">
      <Band lang={lang} label={words.communique.band} />
      <div style={{ padding: "14px 24px 8px", flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <VerdictPill verdict={verdict} lang={lang} />
          <p className="font-display text-xl leading-tight font-extrabold text-balance" data-communique-title>
            {words.communique.title}
          </p>
        </div>
        <div style={{ border: `2px solid ${FILL.false.fill}`, borderRadius: 4, padding: "8px 10px", background: "#ffffff" }}>
          <p className="text-xs font-bold tracking-wide uppercase" style={{ color: RED.ink }}>
            {words.communique.fake}
          </p>
          <p className="mt-1 text-sm leading-snug" style={clamp(4)}>
            <Words
              parts={fake}
              mark={(text) => (
                <s style={{ background: RED.soft, color: RED.ink, textDecorationThickness: 2, fontWeight: 700, padding: "0 2px" }}>{text}</s>
              )}
            />
          </p>
        </div>
        <div style={{ border: `2px solid ${C.ink}`, borderRadius: 4, padding: "8px 10px", background: "#ffffff" }}>
          <p className="text-xs font-bold tracking-wide uppercase">
            {words.communique.original}
            {who && <span style={{ color: C.muted, textTransform: "none", letterSpacing: 0 }}> · {who}</span>}
          </p>
          <p className="mt-1 text-sm leading-snug" style={clamp(4)}>
            <Words parts={original} mark={(text) => <b style={{ textDecoration: "underline", textDecorationThickness: 2, textUnderlineOffset: 3 }}>{text}</b>} />
          </p>
        </div>
      </div>
      <div
        style={{ borderTop: `1px solid ${C.rule}`, margin: "0 24px", padding: "8px 0 12px", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}
      >
        <Byline lang={lang} desk={desk} verified={verified} seal={seal} refLabel={ref} />
        <SealQr seal={seal} size={112} lang={lang} png={qr} />
      </div>
    </div>
  );
}

/** F5: the shareable cards (PNG) and their post text, once a journalist has confirmed the verdict. */
export function VerdictCard({ ws, item, verdict, onShared }: { ws: string; item: Item; verdict: Verdict; onShared?: () => void }) {
  const research = readResearch(item);
  // A dossier that matched a registered original with other words: a doctored communiqué.
  const registry = verdict === "false" && research.registry?.status === "modified" && research.registry.diff.some((d) => d.op !== "equal") ? research.registry : null;
  const [lang, setLang] = useState<Lang>("fr");
  const [format, setFormat] = useState<CardFormat>(registry ? "communique" : "square");
  // The card carries the explanation the journalist signed; the reading's reason is only a fallback
  // for verdicts confirmed before signatures carried one.
  const signedReason = typeof item.data.reason === "string" ? item.data.reason : "";
  const analysisReason = (item.data as { analysis?: { reason?: string } }).analysis?.reason ?? "";
  const [reason, setReason] = useState((signedReason.trim() || analysisReason).slice(0, 280));
  const posts = ((item.data as { posts?: Partial<Record<Lang, string>> }).posts ?? {}) as Partial<Record<Lang, string>>;
  const [post, setPost] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [copied, setCopied] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const { data: sources } = useSWR<Source[]>(`/workspaces/${ws}/sources?item_id=${item.id}`, fetcher);
  const { data: me } = useSWR<Me>("/me", fetcher);
  // The seal exists once the verdict is published by a newsroom that publishes: every format then
  // carries its QR. Before that there is no public page to point to, so no QR.
  const { data: seal } = useSWR<Seal>(item.status === "published" ? `/workspaces/${ws}/items/${item.id}/seal` : null, fetcher, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const qr = useQr(seal?.url, 176);
  const membership = me?.memberships.find((m) => m.workspace_id === ws);
  const desk = membership?.name ?? brand.name;
  const verified = membership?.verification === "approved";
  const text = post ?? posts[lang] ?? "";
  const formats: CardFormat[] = registry ? ["communique", "square", "story"] : ["square", "story"];
  const size = SIZE[format];

  async function write() {
    setWriting(true);
    try {
      const r = await api<{ text: string }>(`/workspaces/${ws}/items/${item.id}/post`, { method: "POST", body: JSON.stringify({ language: lang }) });
      setPost(r.text);
    } catch (e) {
      toast.error(e instanceof ApiError && e.code === "ai_unavailable" ? t.card.aiDown : t.card.failed);
    } finally {
      setWriting(false);
    }
  }

  async function download() {
    if (!cardRef.current || !seal || !qr) return;
    setExporting(true);
    try {
      const url = await toPng(cardRef.current, { width: size.w, height: size.h, pixelRatio: 2, cacheBust: true });
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(item.data as { ref?: string }).ref ?? "verdict"}-${t.card.fileSuffix[format]}-${lang}.png`;
      a.click();
      onShared?.();
    } catch {
      toast.error(t.card.exportFailed);
    } finally {
      setExporting(false);
    }
  }

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success(t.card.copied);
  }

  const props: CardProps = { item, verdict, reason, sources: sources ?? [], lang, desk, verified, seal: seal ?? null, qr };
  const chip = (on: boolean) =>
    cn("h-9 rounded-md border px-3 text-sm font-medium", on ? "border-transparent bg-primary text-primary-foreground" : "border-border bg-card hover:bg-accent");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label={t.card.format}>
          {formats.map((f) => (
            <button key={f} type="button" role="radio" aria-checked={format === f} onClick={() => setFormat(f)} className={chip(format === f)}>
              {t.card.formats[f]}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label={t.card.language}>
          {(["fr", "mg"] as const).map((l) => (
            <button
              key={l}
              type="button"
              role="radio"
              aria-checked={lang === l}
              onClick={() => {
                setLang(l);
                setPost(null);
                setCopied(false);
              }}
              className={chip(lang === l)}
            >
              {t.card.languages[l]}
            </button>
          ))}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{seal ? t.card.sealed : item.status === "published" ? t.card.unsealed : t.card.notPublished}</p>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,540px)_1fr]">
        <div className="justify-self-start overflow-hidden rounded-lg border border-border">
          {/* Exported at full size; shown scaled down on narrow screens and for the tall story. */}
          <div className={cn("origin-top-left max-sm:[zoom:0.6]", format === "story" && "sm:[zoom:0.75]")}>
            <div ref={cardRef} style={{ width: size.w }} data-card-format={format}>
              {format === "story" ? (
                <StoryCard {...props} />
              ) : format === "communique" && registry ? (
                <CommuniqueCard {...props} registry={registry} />
              ) : (
                <SquareCard {...props} />
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="card-reason">{t.card.reason}</Label>
            <textarea
              id="card-reason"
              rows={4}
              maxLength={280}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t.card.reasonPlaceholder}
              className="w-full resize-none rounded-md border border-input bg-card px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
            />
            <p className="text-sm text-muted-foreground tabular">{t.card.chars(reason.length)}</p>
          </div>
          <Button onClick={download} disabled={exporting || !seal || !qr} className="h-10">
            {exporting ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconDownloadSimple aria-hidden />}
            {t.card.downloadAs[format]}
          </Button>

          <div className="space-y-2 border-t border-border pt-4">
            <p className="text-sm font-medium">{t.card.postTitle}</p>
            {text ? (
              <textarea
                aria-label={t.card.postTitle}
                rows={4}
                value={text}
                onChange={(e) => setPost(e.target.value)}
                className="w-full resize-none rounded-md border border-input bg-card px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
              />
            ) : (
              <p className="text-sm text-muted-foreground">{t.card.postEmpty}</p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={write} disabled={writing}>
                {writing ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconSparkle aria-hidden />}
                {text ? t.card.rewrite : t.card.write}
              </Button>
              {text && (
                <Button variant="outline" onClick={copy}>
                  {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
                  {t.card.copy}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
