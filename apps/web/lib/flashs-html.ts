/** A small, script-free public page for a partner radio's daily bulletin. */
export type FlashLine = {
  id: string;
  ref: string | null;
  link: string;
  fr: string;
  mg: string;
  has_audio: boolean;
};

export type FlashData = {
  date: string;
  newsroom: { slug: string; name: string } | null;
  items: FlashLine[];
};

export type Radio = {
  name: string;
  frequency: string | null;
  newsroom: { slug: string; name: string };
};

export type FlashLang = "fr" | "mg" | "en";

export type FlashLabels = {
  title: string;
  lead: string;
  date: (day: string) => string;
  empty: string;
  language: string;
  mgNote: string;
  radio: (name: string) => string;
  radioLead: string;
  markAired: string;
  aired: string;
  airFailed: string;
  badRadio: string;
  failed: string;
  audio: string;
  /** The title with its *word* in italic (falls back to `title`). */
  hero?: string;
};

const LANG_NAMES: Record<FlashLang, string> = { fr: "Français", mg: "Malagasy", en: "English" };
const LOCALES: Record<FlashLang, string> = { fr: "fr-FR", mg: "mg-MG", en: "en-GB" };
const CSS = ":root{color-scheme:light dark;--bg:#f3f2ee;--fg:#0a0a0b;--card:#fbfaf7;--mut:#55544e;--line:rgba(10,10,11,.12)}@media(prefers-color-scheme:dark){:root{--bg:#0a0a0b;--fg:#f3f2ee;--card:#111113;--mut:#a6a5a0;--line:rgba(243,242,238,.12)}}body{font:18px/1.55 system-ui,sans-serif;color:var(--fg);background:var(--bg);margin:0}main{max-width:48rem;margin:auto;padding:1.25rem 1rem 4rem}header{display:flex;gap:1rem;align-items:center;justify-content:space-between;flex-wrap:wrap}header strong{font-size:1.3rem;font-weight:800;letter-spacing:-.04em}nav{display:flex;gap:2px;padding:3px;border:1px solid var(--line);border-radius:2rem;background:var(--card)}nav a{padding:.4rem .85rem;border-radius:2rem;text-decoration:none;font-size:.8rem;font-weight:700}nav a[aria-current]{background:var(--fg);color:var(--bg)}h1{font-size:clamp(2.4rem,9vw,3.8rem);line-height:1;letter-spacing:-.04em;font-weight:800;margin:2.25rem 0 1rem}h1 em{font-family:Georgia,serif;font-weight:500}h2{font-size:1.1rem;margin-top:2rem}ol{padding:0;list-style:none;display:grid;gap:.75rem}li{padding:1.25rem;border:1px solid var(--line);border-radius:1.25rem;background:var(--card);break-inside:avoid}li p:first-child{margin-top:0;font-size:1.2rem}a{color:inherit;text-underline-offset:3px}button{background:var(--fg);color:var(--bg);border:0;border-radius:2rem;padding:.65rem 1.15rem;font:inherit;font-weight:700;cursor:pointer}a:focus-visible,button:focus-visible{outline:3px solid var(--fg);outline-offset:3px}.muted{color:var(--mut)}@media print{:root{--bg:#fff;--fg:#000;--card:#fff;--mut:#333;--line:#999}main{max-width:none;padding:0}.screen{display:none}}";

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] ?? char);
}

function safeLink(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function renderFlashsHtml(input: {
  lang: FlashLang;
  labels: FlashLabels;
  data: FlashData | null;
  radio: Radio | null;
  token: string | null;
  badRadio: boolean;
  mark: "aired" | "failed" | null;
}): string {
  const { lang, labels: l, data, radio, token, badRadio, mark } = input;
  const query = new URLSearchParams(token ? { radio: token } : {});
  const menu = (Object.keys(LANG_NAMES) as FlashLang[]).map((choice) => {
    query.set("lang", choice);
    return `<a href="/flashes?${escapeHtml(query.toString())}" lang="${choice}"${choice === lang ? ' aria-current="page"' : ""}>${LANG_NAMES[choice]}</a>`;
  }).join("");
  const date = data?.date && /^\d{4}-\d{2}-\d{2}$/.test(data.date)
    ? new Date(`${data.date}T12:00:00Z`).toLocaleDateString(LOCALES[lang], { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    : data?.date ?? "";
  const heading = data ? `<h2>${escapeHtml(l.date(date))}${data.newsroom ? ` · ${escapeHtml(data.newsroom.name)}` : ""}</h2>` : "";
  const lines = (data?.items ?? []).map((line) => {
    const spoken = lang === "mg" ? line.mg : line.fr;
    const url = safeLink(line.link);
    const link = url ? `<a href="${escapeHtml(url)}" rel="noreferrer">${escapeHtml(line.ref ?? url)}</a>` : "";
    const audio = line.has_audio && /^[0-9a-f-]{36}$/i.test(line.id)
      ? `<a href="/flashes/audio?id=${encodeURIComponent(line.id)}">${escapeHtml(l.audio)}</a>` : "";
    const action = token && radio ? `<form method="post" action="/flashes?${escapeHtml(new URLSearchParams({ radio: token, lang }).toString())}"><input type="hidden" name="item_id" value="${escapeHtml(line.id)}"><button type="submit">${escapeHtml(l.markAired)}</button></form>` : "";
    return `<li><p lang="${lang === "mg" ? "mg" : "fr"}">${escapeHtml(spoken)}</p><p>${[link, audio].filter(Boolean).join(" · ")}</p>${action}</li>`;
  }).join("");
  const radioName = radio ? `${radio.name}${radio.frequency ? ` ${radio.frequency}` : ""}` : "";
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>${escapeHtml(l.title)} · Checky</title><style>${CSS}</style></head><body><main><header><strong>Checky</strong><nav class="screen" aria-label="${escapeHtml(l.language)}">${menu}</nav></header><h1>${escapeHtml(l.hero ?? l.title).replace(/\*([^*]+)\*/, "<em>$1</em>")}</h1>${radio ? `<p><strong>${escapeHtml(l.radio(radioName))}</strong> · ${escapeHtml(radio.newsroom.name)}</p>` : ""}<p class="muted">${escapeHtml(radio ? l.radioLead : l.lead)}</p>${badRadio ? `<p role="alert">${escapeHtml(l.badRadio)}</p>` : ""}${mark === "failed" ? `<p role="alert">${escapeHtml(l.airFailed)}</p>` : ""}${mark === "aired" ? `<p role="status">${escapeHtml(l.aired)}</p>` : ""}${lang === "mg" ? `<p class="muted">${escapeHtml(l.mgNote)}</p>` : ""}${heading}${data ? data.items.length ? `<ol>${lines}</ol>` : `<p>${escapeHtml(l.empty)}</p>` : `<p role="alert">${escapeHtml(l.failed)}</p>`}</main></body></html>`;
}
