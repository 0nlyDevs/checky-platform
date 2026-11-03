const API = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/public`;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Resolve a short audio link at click time, so expiring storage signatures never enter the page. */
export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  if (!id || !UUID.test(id)) return new Response(null, { status: 404 });
  try {
    const response = await fetch(`${API}/verdicts/${id}`, { cache: "no-store", signal: AbortSignal.timeout(7000) });
    if (!response.ok) return new Response(null, { status: 404 });
    const verdict: unknown = await response.json();
    if (!verdict || typeof verdict !== "object" || !("voice_note" in verdict)) return new Response(null, { status: 404 });
    const note = verdict.voice_note;
    if (!note || typeof note !== "object" || !("url" in note) || typeof note.url !== "string") return new Response(null, { status: 404 });
    const url = new URL(note.url);
    if (url.protocol !== "https:" && url.protocol !== "http:") return new Response(null, { status: 404 });
    return new Response(null, { status: 302, headers: { Location: url.href, "Referrer-Policy": "no-referrer", "Cache-Control": "no-store" } });
  } catch {
    return new Response(null, { status: 404 });
  }
}
