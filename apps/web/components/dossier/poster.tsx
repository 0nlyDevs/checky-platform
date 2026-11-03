"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconArrowLeft, IconDownloadSimple } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { Formats } from "./types";

const p = t.dossier.poster;

// The poster alone on an A4 page, whatever shell is around it.
const PRINT_CSS = `
@media print {
  @page { size: A4 portrait; margin: 0; }
  body * { visibility: hidden !important; }
  .poster-sheet, .poster-sheet * { visibility: visible !important; }
  .poster-sheet { position: absolute !important; inset: 0 auto auto 0 !important; width: 210mm !important; height: 297mm !important; margin: 0 !important; box-shadow: none !important; border: 0 !important; }
}`;

/**
 * The printable poster of a published verdict: the rumour, the verdict as icon and word, the
 * explanation, and a QR code to the public page, for the fokontany, the market, the school.
 */
export function PosterView() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const { data, error } = useSWR<Formats>(`/workspaces/${ws}/items/${id}/diffusion`, fetcher, { revalidateOnFocus: false });
  const [qr, setQr] = useState<string | null>(null);
  const poster = data?.poster;

  useEffect(() => {
    if (!poster) return;
    let live = true;
    QRCode.toDataURL(poster.qr_url, { margin: 1, width: 560, errorCorrectionLevel: "M", color: { dark: "#0a0a0b", light: "#ffffff" } })
      .then((url) => live && setQr(url))
      .catch(() => live && setQr(null));
    return () => {
      live = false;
    };
  }, [poster]);

  const m = poster ? VERDICT_META[poster.verdict] : null;
  const Icon = m?.icon;

  return (
    <div className="mx-auto max-w-[60rem] px-4 pt-6 pb-16 lg:px-8">
      <style>{PRINT_CSS}</style>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href={`/w/${ws}/affirmations/${id}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <IconArrowLeft className="size-4" aria-hidden />
          {p.back}
        </Link>
        {poster && (
          <Button onClick={() => window.print()}>
            <IconDownloadSimple aria-hidden />
            {p.print}
          </Button>
        )}
      </div>
      {poster && <p className="mt-2 text-sm text-muted-foreground">{p.hint}</p>}

      {error && <p className="mt-8 text-muted-foreground">{p.notReady}</p>}
      {!data && !error && <Skeleton aria-label={p.loading} className="mx-auto mt-6 aspect-[210/297] w-full max-w-[42rem]" />}

      {poster && m && Icon && (
        <article
          aria-label={`${p.checkedBy(poster.newsroom)} · ${poster.verdict_word}`}
          className="poster-sheet mx-auto mt-6 flex aspect-[210/297] w-full max-w-[42rem] flex-col bg-white p-[6%] text-[#0a0a0b] shadow-sm ring-1 ring-border"
        >
          <header className="flex items-baseline justify-between gap-4 border-b-2 border-[#0a0a0b] pb-[3%] font-display">
            <span className="text-[clamp(0.9rem,2.4vw,1.35rem)] font-extrabold">{p.checkedBy(poster.newsroom)}</span>
            {poster.ref && <span className="text-[clamp(0.8rem,2vw,1.1rem)] font-bold tabular">{poster.ref}</span>}
          </header>

          <p className="mt-[5%] text-[clamp(0.85rem,2.2vw,1.2rem)] font-bold">{p.rumour}</p>
          <p className="mt-[1.5%] font-display text-[clamp(1.2rem,4vw,2.3rem)] leading-tight font-extrabold text-balance">« {poster.title} »</p>

          <div className={cn("mt-[5%] rounded-md border-[3px] border-current px-[5%] py-[4%]", m.soft, m.ink)}>
            <p className="flex items-center gap-[3%] font-display text-[clamp(2.4rem,9vw,5.2rem)] leading-none font-extrabold tracking-tight">
              <Icon className="size-[1em] shrink-0" aria-hidden />
              {poster.verdict_word}
            </p>
            <p className="mt-[2%] text-[clamp(0.9rem,2.4vw,1.35rem)] font-bold">{poster.verdict_word_mg}</p>
          </div>

          <p className="mt-[5%] text-[clamp(0.9rem,2.3vw,1.3rem)] leading-snug text-pretty">{poster.reason}</p>

          <footer className="mt-auto flex items-end justify-between gap-[5%] border-t-2 border-[#0a0a0b] pt-[4%]">
            <div className="min-w-0">
              <p className="text-[clamp(0.85rem,2.2vw,1.2rem)] font-bold text-pretty">{p.scan}</p>
              {poster.check_label && <p className="mt-[3%] font-display text-[clamp(1.1rem,3.2vw,1.9rem)] leading-none font-extrabold tabular">{poster.check_label}</p>}
              {poster.short_link && <p className="mt-[3%] font-display text-[clamp(1rem,2.8vw,1.6rem)] font-extrabold break-all">{poster.short_link.replace(/^https?:\/\//, "")}</p>}
              {poster.date && <p className="mt-[2%] text-[clamp(0.75rem,1.8vw,1rem)]">{poster.date}</p>}
            </div>
            {qr ? (
              // A data URL drawn here: next/image has nothing to optimise.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr} alt={poster.qr_url} className="aspect-square w-[32%] shrink-0" />
            ) : (
              <span className="aspect-square w-[32%] shrink-0 bg-[#f3f2ee]" aria-hidden />
            )}
          </footer>
        </article>
      )}
    </div>
  );
}
