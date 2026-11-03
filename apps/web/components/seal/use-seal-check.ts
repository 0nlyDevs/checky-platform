"use client";

import { useEffect, useState } from "react";
import type { PublicSeal } from "@/components/registre/types";
import { ApiError } from "@/lib/api";
import { isOffline } from "@/lib/offline";
import { publicApi } from "@/lib/public-api";
import { checkSeal, parseSeal, type ParsedSeal, type SealCheck } from "@/lib/seal";
import { loadSealKeys } from "@/lib/seal-keys";

export type SealOutcome =
  | { phase: "checking" }
  /** Not a seal QR, or an old one checked online that the server does not know. */
  | { phase: "none" }
  /** An old signature-only QR read with no network. */
  | { phase: "needs_network" }
  | { phase: "failed" }
  | {
      phase: "done";
      parsed: ParsedSeal;
      check: SealCheck;
      /** Checked on this device (with the keys of `keysAt`) or, for a browser without Ed25519, by the server. */
      where: "device" | "server";
      keysAt: string | null;
      keysFresh: boolean;
      /** Compared with the registry or the published verdict once online: null until then. */
      record: { same: boolean; current?: boolean } | null;
      /** The communiqué as the registry holds it (online only). */
      seal: PublicSeal | null;
    };

type VerdictVerify = { valid: boolean; revoked: boolean; current: boolean };
type CommuniqueVerify = { valid: boolean; revoked: boolean; matches_record: boolean };

/** Checks the seal in `url` (a QR's text, or the page's own address): first on the device with
 *  the kept keys, no network needed; then, online, against the record. */
export function useSealCheck(url: string | null): SealOutcome {
  const [outcome, setOutcome] = useState<SealOutcome>({ phase: "checking" });

  useEffect(() => {
    if (url === null) return;
    let live = true;
    const set = (o: SealOutcome) => live && setOutcome(o);
    (async () => {
      set({ phase: "checking" });
      const parsed = parseSeal(url, typeof window === "undefined" ? undefined : window.location.origin);
      if (!parsed) return set({ phase: "none" });

      if (parsed.form === "signature") {
        // A QR printed before the seal carried its message: the registry's copy is needed.
        if (isOffline()) return set({ phase: "needs_network" });
        try {
          const seal = await publicApi<PublicSeal>(`/sceau/${encodeURIComponent(parsed.id)}`);
          const full = { form: "full" as const, kind: "communique" as const, id: parsed.id, message: seal.message, payload: JSON.parse(seal.message), signature: parsed.signature, keyId: seal.key_id };
          const key = { key_id: seal.key_id, issuer: seal.payload.issuer ?? "", kind: "communique" as const, public_key: seal.public_key, newsroom: seal.newsroom };
          const revoked = seal.revoked_at ? [{ ...key, revoked_at: seal.revoked_at }] : [];
          let check = await checkSeal(full, { keys: revoked.length ? [] : [key], revoked });
          let where: "device" | "server" = "device";
          if (check.status === "unsupported") {
            const server = await publicApi<CommuniqueVerify>(`/sceau/${encodeURIComponent(parsed.id)}/verify`, { method: "POST", body: JSON.stringify({ signature: parsed.signature }) });
            check = { ...check, status: server.revoked ? "revoked" : server.valid ? "authentic" : "mismatch" };
            where = "server";
          }
          return set({ phase: "done", parsed: full, check, where, keysAt: null, keysFresh: true, record: { same: true }, seal });
        } catch (e) {
          return set({ phase: e instanceof ApiError && (e.status === 404 || e.status === 422) ? "none" : "failed" });
        }
      }

      const keys = await loadSealKeys();
      let check = await checkSeal(parsed, keys ?? { keys: [], revoked: [] });
      let where: "device" | "server" = "device";
      const base = { phase: "done" as const, parsed, keysAt: keys?.at ?? null, keysFresh: Boolean(keys?.fresh), seal: null, record: null };
      set({ ...base, check, where });
      if (isOffline()) return;

      // Online: the record too (and the server's check where this browser has no Ed25519).
      const fragment = { message: parsed.message, signature: parsed.signature, key_id: parsed.keyId };
      try {
        if (parsed.kind === "communique") {
          const id = encodeURIComponent(parsed.id);
          const [seal, server] = await Promise.all([
            publicApi<PublicSeal>(`/sceau/${id}`).catch(() => null),
            publicApi<CommuniqueVerify>(`/sceau/${id}/verify`, { method: "POST", body: JSON.stringify(fragment) }).catch(() => null),
          ]);
          if (server && (check.status === "unsupported" || check.status === "unknown_key")) {
            check = { ...check, status: server.revoked ? "revoked" : server.valid ? "authentic" : "mismatch" };
            where = "server";
          }
          set({ ...base, check, where, seal, record: server ? { same: server.matches_record } : null });
        } else {
          const server = await publicApi<VerdictVerify>(`/sceau/v/${encodeURIComponent(parsed.id)}/verify`, { method: "POST", body: JSON.stringify(fragment) });
          if (check.status === "unsupported" || check.status === "unknown_key") {
            check = { ...check, status: server.revoked ? "revoked" : server.valid ? "authentic" : "mismatch" };
            where = "server";
          }
          set({ ...base, check, where, record: { same: server.valid, current: server.current } });
        }
      } catch {
        // the device's answer stands
      }
    })();
    return () => {
      live = false;
    };
  }, [url]);

  return url === null ? { phase: "checking" } : outcome;
}
