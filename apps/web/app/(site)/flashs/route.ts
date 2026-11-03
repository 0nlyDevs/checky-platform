import { en } from "@/lib/i18n/en";
import { fr } from "@/lib/i18n/fr";
import { mg } from "@/lib/i18n/mg";
import { renderFlashsHtml, type FlashData, type FlashLang, type FlashLine, type Radio } from "@/lib/flashs-html";

const API = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/public`;
const TOKEN = /^[A-Za-z0-9_-]{12,100}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LANGS: FlashLang[] = ["fr", "mg", "en"];

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isRadio(value: unknown): value is Radio {
  return object(value) && typeof value.name === "string" &&
    (value.frequency === null || typeof value.frequency === "string") &&
    object(value.newsroom) && typeof value.newsroom.slug === "string" && typeof value.newsroom.name === "string";
}

function isLine(value: unknown): value is FlashLine {
  return object(value) && typeof value.id === "string" &&
    (value.ref === null || typeof value.ref === "string") &&
    typeof value.link === "string" && typeof value.fr === "string" &&
    typeof value.mg === "string" && typeof value.has_audio === "boolean";
}

function isFlashData(value: unknown): value is FlashData {
  return object(value) && typeof value.date === "string" &&
    (value.newsroom === null || (object(value.newsroom) && typeof value.newsroom.slug === "string" && typeof value.newsroom.name === "string")) &&
    Array.isArray(value.items) && value.items.length <= 20 && value.items.every(isLine);
}

async function publicGet(path: string): Promise<unknown> {
  const response = await fetch(`${API}${path}`, { cache: "no-store", signal: AbortSignal.timeout(7000) });
  if (!response.ok) throw new Error(`Public API ${response.status}`);
  return response.json() as Promise<unknown>;
}

function language(request: Request, url: URL): FlashLang {
  const chosen = url.searchParams.get("lang") ?? request.headers.get("cookie")?.match(/(?:^|;\s*)checky:lang=(fr|mg|en)\b/)?.[1];
  return LANGS.find((lang) => lang === chosen) ?? "fr";
}

function radioToken(url: URL): string | null {
  const token = url.searchParams.get("radio");
  return token && TOKEN.test(token) ? token : null;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const lang = language(request, url);
  const token = radioToken(url);
  let radio: Radio | null = null;
  let badRadio = Boolean(url.searchParams.has("radio") && !token);
  if (token) {
    try {
      const value = await publicGet(`/radios/${encodeURIComponent(token)}`);
      radio = isRadio(value) ? value : null;
      badRadio = !radio;
    } catch {
      badRadio = true;
    }
  }
  let data: FlashData | null = null;
  try {
    const filter = radio ? `?newsroom=${encodeURIComponent(radio.newsroom.slug)}` : "";
    const value = await publicGet(`/flashs${filter}`);
    data = isFlashData(value) ? value : null;
  } catch {
    // The page still explains the unavailable feed in the selected language.
  }
  const labels = {
    ...fr.publicLayer.flashs,
    ...(lang === "mg" ? mg.publicLayer?.flashs : lang === "en" ? en.publicLayer?.flashs : {}),
    hero: (lang === "mg" ? mg.look?.flashs?.hero : lang === "en" ? en.look?.flashs?.hero : undefined) ?? fr.look.flashs.hero,
  };
  const mark = url.searchParams.get("mark");
  const html = renderFlashsHtml({ lang, labels, data, radio, token: radio ? token : null, badRadio, mark: mark === "aired" || mark === "failed" ? mark : null });
  const headers = new Headers({
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
  });
  if (url.searchParams.has("lang")) headers.set("Set-Cookie", `checky:lang=${lang}; Path=/; Max-Age=31536000; SameSite=Lax`);
  return new Response(html, { headers });
}

export async function POST(request: Request) {
  const url = new URL(request.url);
  const token = radioToken(url);
  const origin = request.headers.get("origin");
  if (!token || (origin && origin !== url.origin)) return new Response(null, { status: 403 });
  if (!request.headers.get("content-type")?.startsWith("application/x-www-form-urlencoded")) return new Response(null, { status: 415 });
  const form = await request.formData();
  const item = form.get("item_id");
  if (typeof item !== "string" || !UUID.test(item)) return new Response(null, { status: 422 });
  let mark = "failed";
  try {
    const response = await fetch(`${API}/radios/${encodeURIComponent(token)}/diffuse`, {
      method: "POST", cache: "no-store", signal: AbortSignal.timeout(7000),
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_id: item }),
    });
    if (response.ok) mark = "aired";
  } catch {
    // The presenter can retry from the same text-only page.
  }
  const next = new URL("/flashs", url.origin);
  next.searchParams.set("radio", token);
  next.searchParams.set("lang", language(request, url));
  next.searchParams.set("mark", mark);
  return Response.redirect(next, 303);
}
