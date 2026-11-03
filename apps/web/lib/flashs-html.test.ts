import assert from "node:assert/strict";
import { test } from "node:test";
import { renderFlashsHtml, type FlashData, type FlashLabels } from "./flashs-html.ts";

const labels: FlashLabels = {
  title: "Flashs du jour", lead: "Verdicts signés", date: (date) => `Verdicts du ${date}`,
  empty: "Aucun verdict", language: "Langue", mgNote: "À relire", radio: (name) => `Pour ${name}`,
  radioLead: "Marquez les flashs diffusés", markAired: "Diffusé", aired: "Diffusé",
  airFailed: "Réessayez", badRadio: "Lien non valable", failed: "Impossible de charger",
  audio: "Écouter la rédaction",
};

test("the full daily bulletin stays below 20 KB without scripts or bundles", () => {
  const data: FlashData = {
    date: "2026-11-03", newsroom: { slug: "radio", name: "Radio Démo" },
    items: Array.from({ length: 20 }, (_, i) => ({
      id: `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`,
      ref: `FAN-${String(i).padStart(4, "0")}`,
      link: `https://checky.example/v/${i}`,
      fr: `Faux — ${"Un message daté circule dans la région. ".repeat(5)} (vérification ${i})`,
      mg: `Diso — ${"Hafatra misy daty miparitaka eto amin'ny faritra. ".repeat(5)} (fanamarinana ${i})`,
      has_audio: true,
    })),
  };
  const html = renderFlashsHtml({ lang: "fr", labels, data, radio: { name: "Radio Démo", frequency: "101 FM", newsroom: data.newsroom! }, token: "a_valid_token_123", badRadio: false, mark: null });
  assert.ok(new TextEncoder().encode(html).byteLength < 20_000);
  assert.doesNotMatch(html, /<script|javascript:|_next\//i);
  assert.match(html, /method="post"/);
  assert.match(html, /flashes\/audio\?id=/);
});

test("untrusted text is escaped and unsafe links are omitted", () => {
  const html = renderFlashsHtml({
    lang: "fr", labels, radio: null, token: null, badRadio: false, mark: null,
    data: { date: "2026-11-03", newsroom: null, items: [{ id: "00000000-0000-0000-0000-000000000001", ref: null, link: "javascript:alert(1)", fr: "<script>alert('x')</script>", mg: "", has_audio: false }] },
  });
  assert.doesNotMatch(html, /<script|href="javascript:/i);
  assert.match(html, /&lt;script&gt;/);
});
