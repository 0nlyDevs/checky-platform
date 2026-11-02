import { API_URL, ApiError, getApiToken } from "@/lib/api";

/**
 * POST that answers with Server-Sent Events (EventSource only does GET).
 * Calls `on(event, data)` for every event until the stream ends.
 */
export async function postStream(
  path: string,
  body: unknown,
  on: (event: string, data: unknown) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    method: "POST",
    // the public routes need no account
    headers: path.startsWith("/public/")
      ? { "Content-Type": "application/json" }
      : { "Content-Type": "application/json", Authorization: `Bearer ${await getApiToken()}` },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null);
    throw new ApiError(res.status, err?.error?.code ?? "http_error", err?.error?.message ?? res.statusText);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) on(event, JSON.parse(data.join("\n")));
    }
  }
}
