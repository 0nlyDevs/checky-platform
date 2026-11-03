"use client";

import { useState } from "react";
import { SWRConfig, type Middleware } from "swr";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n";
import { IconImage } from "@/lib/icons";
import { useEco } from "@/lib/prefs";
import { cn } from "@/lib/utils";

/** In Mode éco a polled list asks four times less often (at least a minute apart) and not on focus. */
const SLOWER = 4;
const FLOOR_MS = 60_000;
const slower = (ms: number) => (ms > 0 ? Math.max(ms * SLOWER, FLOOR_MS) : ms);

export const ecoPolling: Middleware = (useSWRNext) => (key, fetcher, config) => {
  const eco = useEco();
  const ri = config.refreshInterval;
  const refreshInterval = !eco ? ri : typeof ri === "function" ? (data: Parameters<typeof ri>[0]) => slower(ri(data)) : typeof ri === "number" ? slower(ri) : ri;
  return useSWRNext(key, fetcher, eco ? { ...config, refreshInterval, revalidateOnFocus: false } : config);
};

/** Every SWR hook below follows Mode éco (root layout). */
export function EcoProvider({ children }: { children: React.ReactNode }) {
  return <SWRConfig value={{ use: [ecoPolling] }}>{children}</SWRConfig>;
}

type Kind = "image" | "map" | "video" | "audio";

/**
 * Something heavy (a map, a video, a photo) that waits for a tap in Mode éco. Outside Mode éco it
 * renders its children at once. The placeholder takes the space given by `className`, so nothing
 * shifts when the real thing loads.
 */
export function EcoGate({ kind, className, children }: { kind: Kind; className?: string; children: React.ReactNode }) {
  const eco = useEco();
  const r = useT().reach.eco;
  const [shown, setShown] = useState(false);
  if (!eco || shown) return <>{children}</>;
  const [note, action] =
    kind === "map" ? [r.mapHidden, r.showMap] : kind === "video" ? [r.imageHidden, r.showVideo] : kind === "audio" ? [r.imageHidden, r.showAudio] : [r.imageHidden, r.showImage];
  return (
    <div className={cn("eco-hold", className)}>
      {kind !== "video" && kind !== "audio" && <span>{note}</span>}
      <Button type="button" variant="outline" size="sm" onClick={() => setShown(true)}>
        {kind === "image" && <IconImage className="size-4" aria-hidden />}
        {action}
      </Button>
    </div>
  );
}

/**
 * An image with explicit dimensions (no layout shift), lazy, and on demand in Mode éco.
 * Use it for photos and thumbnails; small inline QR codes drawn locally need not wait.
 */
export function EcoImage({
  src,
  alt,
  width,
  height,
  className,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  className?: string;
}) {
  return (
    <EcoGate kind="image" className={className}>
      {/* eslint-disable-next-line @next/next/no-img-element -- presigned storage URLs, not optimisable */}
      <img src={src} alt={alt} width={width} height={height} loading="lazy" decoding="async" className={className} />
    </EcoGate>
  );
}
