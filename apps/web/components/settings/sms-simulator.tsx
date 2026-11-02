"use client";

import { useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconCircleNotch, IconPaperPlaneTilt } from "@/lib/icons";
import { cn } from "@/lib/utils";

const s = t.team.settings.sms;
const DEMO_FROM = "+261 34 00 000 09";
const time = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

type Sms = { id: string; direction: "in" | "out"; masked: string; text: string; status: string; created_at: string };
type Simulated = { inbound: { action: string; reply: string; masked: string }; replies: Sms[] };
type Bubble = { id: string; mine: boolean; text: string; note?: string };

/**
 * The SMS line, tried from the desk: a phone-shaped form that writes from the fictional block
 * (+261 34 00 000 xx) through the gateway's own handling, the secret kept on the server. Replies
 * to fictional numbers are stored as `simulated` and never handed to the gateway.
 */
export function SmsSimulator({ ws }: { ws: string }) {
  const [from, setFrom] = useState(DEMO_FROM);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thread, setThread] = useState<Bubble[]>([]);
  const log = useSWR<Sms[]>(`/workspaces/${ws}/sms/messages?limit=12`, fetcher);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<Simulated>(`/workspaces/${ws}/sms/simulate`, { method: "POST", body: JSON.stringify({ from, text: body }) });
      const replies = res.replies.length ? res.replies.map((r) => r.text) : [res.inbound.reply];
      setThread((all) => [
        ...all,
        { id: `${Date.now()}-in`, mine: true, text: body },
        ...replies.map((r, i) => ({ id: `${Date.now()}-out-${i}`, mine: false, text: r, note: i === 0 ? s.actions[res.inbound.action] : undefined })),
      ]);
      setText("");
      void log.mutate();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      const status = err instanceof ApiError ? err.status : 0;
      setError(code === "sms_not_configured" ? s.off : code === "fictional_only" || code === "invalid_number" ? s.fictional : status === 429 ? s.tooMany : s.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="sms-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="sms-title" className="font-semibold">
        {s.title}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{s.lead}</p>
      <div className="mt-5 grid gap-8 md:grid-cols-[18rem_minmax(0,1fr)]">
        {/* A plain phone: the screen holds the conversation, the keypad is the form. */}
        <div className="mx-auto w-full max-w-[18rem] rounded-[2rem] border-4 border-foreground bg-background p-3" aria-label={s.phone} role="group">
          <div className="mx-auto mb-2 h-1.5 w-14 rounded-full bg-foreground" aria-hidden />
          <ol className="flex h-72 flex-col gap-2 overflow-y-auto rounded-xl border border-border bg-card p-2.5" aria-live="polite">
            {!thread.length && <li className="m-auto text-center text-sm text-muted-foreground">{s.empty}</li>}
            {thread.map((m) => (
              <li key={m.id} className={cn("max-w-[85%]", m.mine ? "self-end" : "self-start")}>
                <p className={cn("rounded-lg px-3 py-2 text-sm leading-snug break-words", m.mine ? "bg-foreground text-background" : "bg-muted text-foreground")}>{m.text}</p>
                {m.note && <p className="mt-0.5 text-xs text-muted-foreground">{m.note}</p>}
              </li>
            ))}
          </ol>
          <form onSubmit={send} className="mt-3 space-y-2">
            <label className="block">
              <span className="text-xs font-medium">{s.from}</span>
              <input
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                inputMode="tel"
                maxLength={40}
                className="mt-0.5 h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm tabular outline-none focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium">{s.text}</span>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                maxLength={480}
                placeholder={s.placeholder}
                className="mt-0.5 block w-full resize-none rounded-md border border-input bg-background px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
              />
            </label>
            {error && (
              <p className="text-sm font-bold text-verdict-false-ink" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" variant="outline" className="h-10 w-full" disabled={busy || !text.trim()}>
              {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPaperPlaneTilt aria-hidden />}
              {busy ? s.sending : s.send}
            </Button>
          </form>
          <div className="mx-auto mt-3 h-1 w-20 rounded-full bg-border" aria-hidden />
        </div>

        <div className="min-w-0">
          <p className="text-sm text-pretty text-muted-foreground">{s.keywords}</p>
          <h3 className="mt-5 text-sm font-medium">{s.log}</h3>
          {log.data && !log.data.length && <p className="mt-2 text-sm text-muted-foreground">{s.logEmpty}</p>}
          <ul className="mt-2 divide-y divide-border rounded-md border border-border">
            {log.data?.map((m) => (
              <li key={m.id} className="px-3 py-2.5 text-sm">
                <p className="flex flex-wrap justify-between gap-x-3 text-muted-foreground">
                  <span>
                    {s.direction[m.direction]} <span className="tabular">{m.masked}</span>
                  </span>
                  <span className="tabular">
                    {time.format(new Date(m.created_at))} · {s.status[m.status] ?? m.status}
                  </span>
                </p>
                <p className="mt-0.5 break-words text-pretty">{m.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
