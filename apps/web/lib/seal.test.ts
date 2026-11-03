import assert from "node:assert/strict";
import { test } from "node:test";
import { checkNumber, checkSeal, parseSeal, type SealKeys } from "./seal.ts";

const b64u = (bytes: Uint8Array | string) =>
  Buffer.from(typeof bytes === "string" ? new TextEncoder().encode(bytes) : bytes)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

async function issuer(kind: "verdict" | "communique") {
  const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
  const raw = new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey));
  const key = { key_id: "k_test", issuer: kind === "verdict" ? "checky:verdicts" : "JIRAMA", kind, public_key: Buffer.from(raw).toString("base64"), newsroom: { slug: "r", name: "R" } };
  const sign = async (message: string) => b64u(new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, pair.privateKey, new TextEncoder().encode(message))));
  return { key, sign };
}

// The API's canonical JSON: sorted keys, no spaces, UTF-8 kept.
const COMMUNIQUE = '{"fingerprint":"ab12","issued_on":"2026-11-01","issuer":"JIRAMA","number":"2026-118","title":"Délestage (démo)"}';

test("a communiqué QR is checked offline from its fragment and the cached keys", async () => {
  const { key, sign } = await issuer("communique");
  const keys: SealKeys = { keys: [key], revoked: [] };
  const url = `https://checky.mg/sceau/c1#${b64u(COMMUNIQUE)}.${await sign(COMMUNIQUE)}.k_test`;
  const seal = parseSeal(url);
  assert.ok(seal && seal.form === "full");
  assert.equal(seal.payload.number, "2026-118");
  assert.equal(seal.payload.title, "Délestage (démo)");
  assert.equal((await checkSeal(seal, keys)).status, "authentic");

  // The same signature over other words (a number changed on the fake) does not fit.
  const forged = COMMUNIQUE.replace("2026-118", "2026-119");
  const tampered = parseSeal(`https://checky.mg/sceau/c1#${b64u(forged)}.${await sign(COMMUNIQUE)}.k_test`);
  assert.ok(tampered && tampered.form === "full");
  assert.equal((await checkSeal(tampered, keys)).status, "mismatch");

  const revoked = { ...key, revoked_at: "2026-11-02T08:00:00Z" };
  assert.equal((await checkSeal(seal, { keys: [], revoked: [revoked] })).status, "revoked");
  assert.equal((await checkSeal(seal, { keys: [], revoked: [] })).status, "unknown_key");
});

test("a verdict QR must name the page it is on and be signed by a verdict key", async () => {
  const { key, sign } = await issuer("verdict");
  const message = '{"digest":"d","id":"v1","ref":"FAN-0145","signed_at":"2026-11-02T05:15Z","title":"T","type":"verdict","verdict":"false"}';
  const fragment = `${b64u(message)}.${await sign(message)}.k_test`;
  const seal = parseSeal(`https://checky.mg/verifies/v1#${fragment}`);
  assert.ok(seal && seal.form === "full");
  assert.equal((await checkSeal(seal, { keys: [key], revoked: [] })).status, "authentic");
  // Glued on another verdict's page.
  const elsewhere = parseSeal(`https://checky.mg/verifies/v2#${fragment}`);
  assert.ok(elsewhere && elsewhere.form === "full");
  assert.equal((await checkSeal(elsewhere, { keys: [key], revoked: [] })).status, "mismatch");
  // A communiqué key with the same id does not count for a verdict.
  assert.equal((await checkSeal(seal, { keys: [{ ...key, kind: "communique" }], revoked: [] })).status, "unknown_key");
  assert.equal(checkNumber(seal.payload.ref), 145);
});

test("old signature-only communiqué QRs and other links are told apart", () => {
  assert.deepEqual(parseSeal("https://checky.mg/sceau/c1#c2lnbmF0dXJl"), { form: "signature", kind: "communique", id: "c1", signature: "c2lnbmF0dXJl" });
  assert.equal(parseSeal("https://checky.mg/verifies/v1"), null);
  assert.equal(parseSeal("https://example.com/hello#a.b.c"), null);
  assert.equal(parseSeal("https://other.example/sceau/c1#c2lnbmF0dXJl", "https://checky.mg"), null);
  // A verdict message on a communiqué page is refused (domain separation).
  const verdict = b64u('{"id":"v1","type":"verdict"}');
  assert.equal(parseSeal(`https://checky.mg/sceau/c1#${verdict}.sig.k`), null);
});

test("the English addresses read like the French ones printed before them", async () => {
  const { key, sign } = await issuer("communique");
  const keys: SealKeys = { keys: [key], revoked: [] };
  const seal = parseSeal(`https://checky.mg/seal/c1#${b64u(COMMUNIQUE)}.${await sign(COMMUNIQUE)}.k_test`);
  assert.ok(seal && seal.form === "full" && seal.kind === "communique");
  assert.equal((await checkSeal(seal, keys)).status, "authentic");

  const verdictKey = await issuer("verdict");
  const message = '{"digest":"d","id":"v1","ref":"FAN-0145","signed_at":"2026-11-02T05:15Z","title":"T","type":"verdict","verdict":"false"}';
  const fragment = `${b64u(message)}.${await verdictKey.sign(message)}.k_test`;
  const verdict = parseSeal(`https://checky.mg/verdicts/v1#${fragment}`);
  assert.ok(verdict && verdict.form === "full" && verdict.kind === "verdict");
  assert.equal((await checkSeal(verdict, { keys: [verdictKey.key], revoked: [] })).status, "authentic");
  const elsewhere = parseSeal(`https://checky.mg/verdicts/v2#${fragment}`);
  assert.ok(elsewhere && elsewhere.form === "full");
  assert.equal((await checkSeal(elsewhere, { keys: [verdictKey.key], revoked: [] })).status, "mismatch");

  assert.deepEqual(parseSeal("https://checky.mg/seal/c1#c2lnbmF0dXJl"), { form: "signature", kind: "communique", id: "c1", signature: "c2lnbmF0dXJl" });
  assert.equal(parseSeal("https://checky.mg/verdicts/v1"), null);
  assert.equal(parseSeal(`https://checky.mg/seal/c1#${b64u('{"id":"v1","type":"verdict"}')}.sig.k`), null);
});
