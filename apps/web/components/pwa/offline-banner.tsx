"use client";

import { useEffect } from "react";
import { warmPages } from "@/components/pwa/service-worker";
import { api } from "@/lib/api";
import { useMoment, useT } from "@/lib/i18n";
import { IconWifiSlash } from "@/lib/icons";
import { useCachedSince, useMissing, useOnline } from "@/lib/offline";
import { loadSealKeys } from "@/lib/seal-keys";
import { cn } from "@/lib/utils";

/** « Hors connexion · données du … »: shown while there is no network, with the age of what is on
 *  screen (the oldest saved answer the page shows) and what still works. */
export function OfflineBanner({ scope, className }: { scope: "desk" | "site"; className?: string }) {
  const online = useOnline();
  const since = useCachedSince();
  const missing = useMissing();
  const b = useT().offline.banner;
  const moment = useMoment();
  if (online) return null;
  return (
    <p role="status" data-offline-banner className={cn("flex flex-wrap items-center gap-x-2 gap-y-0.5 bg-foreground px-4 py-2 text-sm text-background print:hidden", className)}>
      <IconWifiSlash className="size-4 shrink-0" aria-hidden />
      <strong>{b.off}</strong>
      {since ? <span>· {b.since(moment(since))}</span> : missing > 0 ? <span>· {b.noData}</span> : null}
      <span className="basis-full sm:basis-auto sm:before:content-['·_']">{scope === "desk" ? b.desk : b.site}</span>
    </p>
  );
}

const WARM_KEY = "checky:warmed";
const WARM_EVERY_MS = 30 * 60_000;

/** Online, at most every 30 minutes: keeps the correspondent's pages and their data on the device
 *  (the service worker saves what these reads answer), so the desk opens with no network. */
export function OfflineWarmup({ ws }: { ws: string }) {
  const online = useOnline();
  useEffect(() => {
    if (!online) return;
    try {
      const last = Number(sessionStorage.getItem(`${WARM_KEY}:${ws}`) ?? 0);
      if (Date.now() - last < WARM_EVERY_MS) return;
      sessionStorage.setItem(`${WARM_KEY}:${ws}`, String(Date.now()));
    } catch {
      return;
    }
    const timer = setTimeout(() => {
      const w = `/w/${ws}`;
      void warmPages(["beat", "verify", "scanner", "claims", "watch", "directory", "figures", "registry"].map((p) => `${w}/${p}`).concat("/scanner"));
      // The same paths the pages read, so their saved answers are the ones they ask for.
      const reads = [
        "/me",
        `/workspaces/${ws}`,
        `/workspaces/${ws}/members`,
        `/workspaces/${ws}/me/prefs`,
        `/workspaces/${ws}/items?limit=200&type=claim`,
        `/workspaces/${ws}/rubrique`,
        `/workspaces/${ws}/alerts`,
        `/workspaces/${ws}/contacts`,
        `/workspaces/${ws}/figures`,
        `/workspaces/${ws}/registry?status=original`,
      ];
      for (const path of reads) void api(path).catch(() => null);
      void loadSealKeys();
    }, 4000);
    return () => clearTimeout(timer);
  }, [online, ws]);
  return null;
}
