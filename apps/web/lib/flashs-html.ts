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
};

const LANG_NAMES: Record<FlashLang, string> = { fr: "Français", mg: "Malagasy", en: "English" };
const LOCALES: Record<FlashLang, string> = { fr: "fr-FR", mg: "mg-MG", en: "en-GB" };
const CSS = "body{font:18px/1.5 system-ui,sans-serif;color:#0a0a0b;background:#f3f2ee;margin:0}main{max-width:48rem;margin:auto;padding:1.5rem}header,nav{display:flex;gap:1rem;align-items:center;flex-wrap:wrap}header{border-bottom:2px solid #0a0a0b;padding-bottom:1rem}h1{font-size:2.2rem;line-height:1.1}h2{font-size:1.15rem}ol{padding:0;list-style:none}li{border-top:1px solid #777;padding:1rem 0;break-inside:avoid}a{color:inherit;text-underline-offset:3px}button{background:#0a0a0b;color:#fff;border:0;border-radius:2rem;padding:.6rem 1rem;font:inherit;cursor:pointer}a:focus-visible,button:focus-visible{outline:3px solid #0a0a0b;outline-offset:3px}.muted{color:#414141}@media print{body{background:#fff}main{max-width:none;padding:0}.screen{display:none}}";

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
    return `<a href="/flashs?${escapeHtml(query.toString())}" lang="${choice}"${choice === lang ? ' aria-current="page"' : ""}>${LANG_NAMES[choice]}</a>`;
  }).join(" · ");
  const date = data?.date && /^\d{4}-\d{2}-\d{2}$/.test(data.date)
    ? new Date(`${data.date}T12:00:00Z`).toLocaleDateString(LOCALES[lang], { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    : data?.date ?? "";
  const heading = data ? `<h2>${escapeHtml(l.date(date))}${data.newsroom ? ` · ${escapeHtml(data.newsroom.name)}` : ""}</h2>` : "";
  const lines = (data?.items ?? []).map((line) => {
    const spoken = lang === "mg" ? line.mg : line.fr;
    const url = safeLink(line.link);
    const link = url ? `<a href="${escapeHtml(url)}" rel="noreferrer">${escapeHtml(line.ref ?? url)}</a>` : "";
    const audio = line.has_audio && /^[0-9a-f-]{36}$/i.test(line.id)
      ? `<a href="/flashs/audio?id=${encodeURIComponent(line.id)}">${escapeHtml(l.audio)}</a>` : "";
    const action = token && radio ? `<form method="post" action="/flashs?${escapeHtml(new URLSearchParams({ radio: token, lang }).toString())}"><input type="hidden" name="item_id" value="${escapeHtml(line.id)}"><button type="submit">${escapeHtml(l.markAired)}</button></form>` : "";
    return `<li><p lang="${lang === "mg" ? "mg" : "fr"}">${escapeHtml(spoken)}</p><p>${[link, audio].filter(Boolean).join(" · ")}</p>${action}</li>`;
  }).join("");
  const radioName = radio ? `${radio.name}${radio.frequency ? ` ${radio.frequency}` : ""}` : "";
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>${escapeHtml(l.title)} · Checky</title><style>${CSS}</style></head><body><main><header><strong>Checky</strong><nav class="screen" aria-label="${escapeHtml(l.language)}">${menu}</nav></header><h1>${escapeHtml(l.title)}</h1>${radio ? `<p><strong>${escapeHtml(l.radio(radioName))}</strong> · ${escapeHtml(radio.newsroom.name)}</p>` : ""}<p class="muted">${escapeHtml(radio ? l.radioLead : l.lead)}</p>${badRadio ? `<p role="alert">${escapeHtml(l.badRadio)}</p>` : ""}${mark === "failed" ? `<p role="alert">${escapeHtml(l.airFailed)}</p>` : ""}${mark === "aired" ? `<p role="status">${escapeHtml(l.aired)}</p>` : ""}${lang === "mg" ? `<p class="muted">${escapeHtml(l.mgNote)}</p>` : ""}${heading}${data ? data.items.length ? `<ol>${lines}</ol>` : `<p>${escapeHtml(l.empty)}</p>` : `<p role="alert">${escapeHtml(l.failed)}</p>`}</main></body></html>`;
}
