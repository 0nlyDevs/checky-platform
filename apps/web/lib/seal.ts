/**
 * Seals read from a QR code, checked on the device with no network (Ed25519 in WebCrypto).
 *
 * A seal QR is a public page with everything needed after `#` (the fragment never reaches a server):
 *   verdict card   {web}/verdicts/{id}#<b64u(message)>.<signature>.<key_id>   message has "type":"verdict"
 *   communiqué     {web}/seal/{cid}#<b64u(message)>.<signature>.<key_id>     message has no "type"
 *   old communiqué {web}/seal/{cid}#<signature>                               needs the network
 * `message` is the canonical JSON that was signed (sorted keys, no spaces, UTF-8); the fields shown
 * to compare with the paper are read back from it, so what is displayed is what was signed.
 * No imports: this file runs under `node --test` as is.
 */

export type SealKind = "verdict" | "communique";

export type ParsedSeal =
  | { form: "full"; kind: SealKind; id: string; message: string; payload: Record<string, unknown>; signature: string; keyId: string }
  | { form: "signature"; kind: "communique"; id: string; signature: string };

export type SealKey = { key_id: string; issuer: string; kind: SealKind; public_key: string; newsroom: { slug: string; name: string } };
export type RevokedKey = { key_id: string; issuer: string; kind: SealKind; revoked_at: string; newsroom: { slug: string; name: string } };
export type SealKeys = { keys: SealKey[]; revoked: RevokedKey[] };

/** authentic: signed by a known, current key. mismatch: the signature does not fit these words (or
 *  this page). revoked: the key was withdrawn. unknown_key: no key with this id on the device yet.
 *  unsupported: this browser cannot check Ed25519 (the page asks the server instead). */
export type SealStatus = "authentic" | "mismatch" | "revoked" | "unknown_key" | "unsupported";

export type SealCheck = {
  status: SealStatus;
  kind: SealKind;
  /** The signed fields, read from the QR itself (null for an old signature-only QR). */
  payload: Record<string, unknown> | null;
  key: SealKey | null;
  revoked: RevokedKey | null;
};

const COMMUNIQUE_FIELDS = ["fingerprint", "issued_on", "issuer", "number", "title"];

export function fromB64u(value: string): Uint8Array<ArrayBuffer> {
  const b64 = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
}

export function fromB64(value: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(value), (ch) => ch.charCodeAt(0));
}

/** Reads a seal URL (or a page's path and hash). Null for anything that is not a seal QR. */
export function parseSeal(url: string, base = "https://checky.invalid"): ParsedSeal | null {
  let at: URL;
  try {
    at = new URL(url, base);
  } catch {
    return null;
  }
  // A signed fragment copied onto an unrelated host is not a Checky QR. In the app, `base` is
  // the public site's origin; the default sentinel keeps this parser testable without a browser.
  if (base !== "https://checky.invalid" && at.origin !== new URL(base).origin) return null;
  // Cards and communiqués printed before the English addresses carry /verifies and /sceau: both read.
  const path = at.pathname.match(/\/(verdicts|verifies|seal|sceau)\/([^/]+)\/?$/);
  if (!path) return null;
  const kind: SealKind = path[1] === "verdicts" || path[1] === "verifies" ? "verdict" : "communique";
  const id = decodeURIComponent(path[2]);
  const fragment = decodeURIComponent(at.hash.slice(1));
  if (!fragment) return null;
  const parts = fragment.split(".");
  if (parts.length === 1 && kind === "communique") return { form: "signature", kind, id, signature: parts[0] };
  if (parts.length !== 3) return null;
  const [packed, signature, keyId] = parts;
  let message: string;
  let payload: unknown;
  try {
    message = new TextDecoder("utf-8", { fatal: true }).decode(fromB64u(packed));
    payload = JSON.parse(message);
  } catch {
    return null;
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const fields = payload as Record<string, unknown>;
  if (kind === "verdict" && fields.type !== "verdict") return null;
  if (kind === "communique" && Object.keys(fields).sort().join() !== COMMUNIQUE_FIELDS.join()) return null;
  return { form: "full", kind, id, message, payload: fields, signature, keyId };
}

/** Ed25519 here, with no network. Null when this browser cannot (old WebKit, no secure context). */
export async function verifyEd25519(publicKeyB64: string, message: string, signatureB64u: string): Promise<boolean | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  let key: CryptoKey;
  try {
    key = await subtle.importKey("raw", fromB64(publicKeyB64), { name: "Ed25519" }, false, ["verify"]);
  } catch {
    return null;
  }
  try {
    return await subtle.verify({ name: "Ed25519" }, key, fromB64u(signatureB64u), new TextEncoder().encode(message));
  } catch {
    return false;
  }
}

/** The whole offline check of a full QR against the keys kept on the device. A revoked key is
 *  looked at first: its old seals still verify mathematically, but they are shown as revoked. */
export async function checkSeal(seal: Extract<ParsedSeal, { form: "full" }>, keys: SealKeys): Promise<SealCheck> {
  const base = { kind: seal.kind, payload: seal.payload };
  const revoked = keys.revoked.find((k) => k.key_id === seal.keyId && k.kind === seal.kind) ?? null;
  const key = keys.keys.find((k) => k.key_id === seal.keyId && k.kind === seal.kind) ?? null;
  // A verdict card signs its dossier's id: a real QR glued on another verdict's page does not fit.
  if (seal.kind === "verdict" && seal.payload.id !== seal.id) return { ...base, status: "mismatch", key, revoked };
  if (revoked) return { ...base, status: "revoked", key: null, revoked };
  if (!key) return { ...base, status: "unknown_key", key: null, revoked: null };
  const valid = await verifyEd25519(key.public_key, seal.message, seal.signature);
  return { ...base, status: valid === null ? "unsupported" : valid ? "authentic" : "mismatch", key, revoked: null };
}

/** The verification number said on air for FAN-0145 (`vérification 145`). */
export function checkNumber(ref: unknown): number | null {
  const m = String(ref ?? "").trim().match(/(\d{1,8})$/);
  return m ? Number(m[1]) : null;
}
