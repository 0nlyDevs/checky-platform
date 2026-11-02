"use client";

import type { Item, Me, Verdict } from "@fanilo/shared";
import { toPng } from "html-to-image";
import { useRef, useState } from "react";
import useSWR from "swr";
import { IconCheck, IconCircleNotch, IconCopy, IconDownloadSimple, IconSparkle } from "@/lib/icons";
import { toast } from "sonner";
import { LogoMark } from "@/components/brand/logo";
import { VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, ApiError, fetcher } from "@/lib/api";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";
import type { Source } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Lang = "fr" | "mg";

// The card is a shared artefact: fixed palette from DESIGN.md, the same in light and dark mode.
const C = { band: "#0a0a0b", ground: "#f3f2ee", ink: "#0a0a0b", muted: "#55544e", rule: "#dcdbd5" };
const FILL: Record<Verdict, { fill: string; on: string }> = {
  true: { fill: "#0b6b3a", on: "#ffffff" },
  misleading: { fill: "#8a5700", on: "#ffffff" },
  false: { fill: "#b3231a", on: "#ffffff" },
  unverifiable: { fill: "#1d58c4", on: "#ffffff" },
};

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** 540 × 540 CSS pixels, exported at 2× = 1080 × 1080, the size Facebook and WhatsApp show square. */
function Card({ item, verdict, reason, sources, lang, desk }: { item: Item; verdict: Verdict; reason: string; sources: Source[]; lang: Lang; desk: string }) {
  const m = VERDICT_META[verdict];
  const Icon = m.icon;
  const words = t.card.words[lang];
  const ref = (item.data as { ref?: string }).ref;
  const names = sources.map((s) => (s.url ? host(s.url) : s.title)).filter((v, i, a) => a.indexOf(v) === i).slice(0, 3);
  return (
    <div style={{ width: 540, height: 540, background: C.ground, color: C.ink, display: "flex", flexDirection: "column" }} className="font-sans">
      <div style={{ background: C.band, color: "#f3f2ee", padding: "18px 28px", display: "flex", alignItems: "center", gap: 10 }}>
        <LogoMark className="size-6" />
        <span className="font-display text-xl font-extrabold">{brand.name}</span>
        <span style={{ marginLeft: "auto", opacity: 0.85 }} className="text-sm">
          {words.checked}
        </span>
      </div>
      <div style={{ padding: "26px 28px", flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: 18 }}>
        <div style={{ background: FILL[verdict].fill, color: FILL[verdict].on, borderRadius: 4, padding: "12px 16px", display: "flex", alignItems: "center", gap: 12, alignSelf: "flex-start" }}>
          <Icon className="size-8" aria-hidden />
          <span className="font-display text-4xl leading-none font-extrabold tracking-tight">{words.verdicts[verdict]}</span>
        </div>
        <div>
          <p style={{ color: C.muted }} className="text-sm">
            {words.claim}
          </p>
          <p className="quote mt-1 text-2xl leading-snug text-pretty">« {item.title} »</p>
        </div>
        {reason && <p className="text-lg leading-relaxed text-pretty">{reason}</p>}
        {names.length > 0 && (
          <p style={{ color: C.muted }} className="text-sm">
            {words.sources} : {names.join(" · ")}
          </p>
        )}
      </div>
      <div style={{ borderTop: `1px solid ${C.rule}`, margin: "0 28px", padding: "14px 0 18px", display: "flex", alignItems: "center", gap: 10, color: C.muted }} className="text-sm">
        {ref && <span className="font-display text-base font-bold tabular" style={{ color: C.ink }}>{ref}</span>}
        <span className="truncate">{words.by(desk)}</span>
      </div>
    </div>
  );
}

/** F5: the shareable card (PNG) and its post text, once a journalist has confirmed the verdict. */
export function VerdictCard({ ws, item, verdict, onShared }: { ws: string; item: Item; verdict: Verdict; onShared?: () => void }) {
  const [lang, setLang] = useState<Lang>("fr");
  const analysisReason = ((item.data as { analysis?: { reason?: string } }).analysis?.reason ?? "").slice(0, 280);
  const [reason, setReason] = useState(analysisReason);
  const posts = ((item.data as { posts?: Partial<Record<Lang, string>> }).posts ?? {}) as Partial<Record<Lang, string>>;
  const [post, setPost] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [copied, setCopied] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const { data: sources } = useSWR<Source[]>(`/workspaces/${ws}/sources?item_id=${item.id}`, fetcher);
  const { data: me } = useSWR<Me>("/me", fetcher);
  const desk = me?.memberships.find((m) => m.workspace_id === ws)?.name ?? brand.name;
  const text = post ?? posts[lang] ?? "";

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
    if (!cardRef.current) return;
    setExporting(true);
    try {
      const url = await toPng(cardRef.current, { width: 540, height: 540, pixelRatio: 2, cacheBust: true });
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(item.data as { ref?: string }).ref ?? "verdict"}-${lang}.png`;
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

  return (
    <div className="space-y-5">
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
            className={cn("h-9 rounded-md border px-3 text-sm font-medium", lang === l ? "border-transparent bg-primary text-primary-foreground" : "border-border bg-card hover:bg-accent")}
          >
            {t.card.languages[l]}
          </button>
        ))}
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,540px)_1fr]">
        <div className="overflow-hidden rounded-lg border border-border">
          {/* Exported at full size; shown scaled down on narrow screens. */}
          <div className="origin-top-left max-sm:[zoom:0.6]">
            <div ref={cardRef} className="w-[540px]">
              <Card item={item} verdict={verdict} reason={reason} sources={sources ?? []} lang={lang} desk={desk} />
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
          <Button onClick={download} disabled={exporting} className="h-10">
            {exporting ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconDownloadSimple aria-hidden />}
            {t.card.download}
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
