"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Mic, RotateCcw, Send, Square, X } from "lucide-react";
import { useAssistant } from "@/components/assistant/assistant-context";
import { VerdictChip } from "@/components/claims/verdict";
import { API_URL, ApiError, api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, myTips, publicApi, rememberTip } from "@/lib/public-api";
import { type Lang, speak, stopSpeaking } from "@/lib/speak";
import { postStream } from "@/lib/sse";
import { cn } from "@/lib/utils";

const a = t.assistant;
type Cite = { n: number; title: string; url?: string | null; id?: string; verdict?: PublicVerdict["verdict"] };
type Origin = keyof typeof t.origins;
/** A change the agent proposes; nothing happens until the person confirms it here. */
type Action = {
  id: number;
  kind: "tip" | "navigate" | "create_claim" | "attach_link" | "analyze" | "set_status";
  href?: string;
  label?: string;
  newsroom?: string;
  newsroom_name?: string;
  newsrooms?: { slug: string; name: string }[];
  text?: string;
  url?: string | null;
  origin?: Origin;
  title?: string;
  item_id?: string;
  ref?: string | null;
  status?: keyof typeof t.status;
  state?: "pending" | "running" | "done" | "cancelled" | "failed";
  outcome?: string;
  link?: string;
};
type Turn = {
  id: number;
  question: string;
  answer: string;
  state: "thinking" | "done" | "error";
  steps?: string[];
  cites?: Cite[];
  actions?: Action[];
  note?: string;
};

const YES = /^(oui|ouais|ok|okay|d'accord|dacord|vas[- ]y|envoie|envoyez|confirme|confirmer|c'est bon|eny|eka|ie)\b/i;
const NO = /^(non|annule|annuler|stop|laisse|tsia|aza)\b/i;
const STORE = "fanilo:assistant";

function stored(key: string): Turn[] {
  try {
    return typeof window === "undefined" ? [] : ((JSON.parse(sessionStorage.getItem(key) ?? "{}").turns as Turn[]) ?? []);
  } catch {
    return [];
  }
}

/**
 * The floating site agent on every page. Outside a workspace it is the visitors' guide (published
 * verdicts, tips, their follow-up, the right page); inside one it is the desk's copilot (the desk, its
 * sources, proposed changes). Every change it proposes waits for a click, or a spoken « oui ».
 * Questions can be typed or dictated (French or Malagasy, Whisper); in voice mode answers are read aloud.
 */
export function AssistantWidget({ scope = "public" }: { scope?: "public" | "desk" }) {
  const params = useParams<{ ws?: string }>();
  const ws = scope === "desk" ? params?.ws : undefined;
  const router = useRouter();
  const pathname = usePathname();
  const key = `${STORE}:${ws ?? "public"}`;
  const { open, setOpen } = useAssistant();
  const [text, setText] = useState("");
  // The conversation survives page changes (the agent itself opens pages) for this tab.
  const [turns, setTurns] = useState<Turn[]>(() => stored(key));
  const [loaded, setLoaded] = useState(key);
  if (loaded !== key) {
    // the shell's widget outlives the onboarding page: a workspace has its own conversation
    setLoaded(key);
    setTurns(stored(key));
  }
  const [lang, setLang] = useState<Lang>("fr");
  const [voice, setVoice] = useState(false);
  const [rec, setRec] = useState<"idle" | "listening" | "transcribing">("idle");
  const [speaking, setSpeaking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const micBusy = useRef(false); // one recording at a time, even when two paths ask to listen
  const meter = useRef<HTMLDivElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const seq = useRef(turns.reduce((m, x) => Math.max(m, x.id), 0));
  const pending = useRef<{ turn: number; action: Action } | null>(null);
  const turnsRef = useRef(turns);
  const voiceRef = useRef(voice);
  const openRef = useRef(open);
  // Voice mode chains turns through callbacks made several renders earlier (listen → transcribe →
  // ask → speak → listen): they must read the current page, language and conversation, not the
  // ones of the render that created them (the copilot was told the page before a navigation).
  const pathRef = useRef(pathname);
  const langRef = useRef(lang);
  useEffect(() => {
    pathRef.current = pathname;
    langRef.current = lang;
  }, [pathname, lang]);
  useEffect(() => {
    voiceRef.current = voice;
    openRef.current = open;
    if (!open) {
      if (recorder.current?.state === "recording") recorder.current.stop();
      stopSpeaking();
    }
  }, [voice, open]);
  const canRecord = typeof window !== "undefined" && "MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
    turnsRef.current = turns;
    try {
      sessionStorage.setItem(key, JSON.stringify({ turns: turns.slice(-12), open }));
    } catch {
      // without storage the conversation simply starts again on the next page
    }
  }, [turns, open, key]);
  useEffect(() => {
    // reopen after a page the agent opened (a different layout mounts a new widget)
    try {
      if (JSON.parse(sessionStorage.getItem(key) ?? "{}").open) requestAnimationFrame(() => setOpen(true));
    } catch {
      // nothing to restore
    }
  }, [key, setOpen]);
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [open, setOpen]);
  useEffect(() => () => stopSpeaking(), []);

  const update = (id: number, patch: (x: Turn) => Partial<Turn>) => setTurns((all) => all.map((x) => (x.id === id ? { ...x, ...patch(x) } : x)));

  function history(q: string) {
    const past = turnsRef.current.filter((x) => x.state === "done").slice(-3);
    return [
      ...past.flatMap((x) => {
        const said = [x.answer, ...(x.actions ?? []).map((ac) => ac.outcome)].filter(Boolean).join(" ");
        return [{ role: "user", content: x.question.slice(0, 2000) }, ...(said ? [{ role: "assistant", content: said.slice(0, 2000) }] : [])];
      }),
      { role: "user", content: q.slice(0, 2000) },
    ];
  }

  async function ask(question: string) {
    const q = question.trim();
    if (q.length < 2) return;
    const id = ++seq.current;
    const messages = history(q);
    setTurns((all) => [...all, { id, question: q, answer: "", state: "thinking", steps: [] }]);
    setText("");
    let finalAnswer = "";
    let actions: Action[] = [];
    // In voice mode the agent keeps its answer short: it is read aloud.
    const body = { messages, lang: langRef.current, page: pathRef.current, tips: ws ? [] : myTips().map((x) => x.token), voice: voiceRef.current };
    try {
      await postStream(ws ? `/workspaces/${ws}/copilot` : "/public/agent", body, (event, data) => {
        if (event === "step") update(id, (x) => ({ steps: [...(x.steps ?? []), (data as { summary: string }).summary] }));
        else if (event === "answer") {
          const d = data as { text: string; citations: Cite[]; actions: Action[] };
          finalAnswer = d.text ?? "";
          actions = d.actions.map((ac) => ({ ...ac, state: ac.kind === "navigate" ? "done" : "pending" }));
          update(id, () => ({ answer: finalAnswer, cites: d.citations, actions, state: "done" }));
        } else if (event === "error") update(id, () => ({ state: "error", note: (data as { code?: string }).code === "ai_unavailable" ? a.busy : a.failed }));
      });
    } catch (err) {
      return update(id, () => ({ state: "error", note: err instanceof ApiError && err.status === 429 ? a.tooMany : a.failed }));
    }
    const go = actions.find((ac) => ac.kind === "navigate");
    if (go?.href && go.href !== pathRef.current) router.push(go.href as never);
    const waiting = actions.find((ac) => ac.state === "pending");
    pending.current = waiting ? { turn: id, action: waiting } : null;
    if (voiceRef.current && finalAnswer) say(waiting ? `${finalAnswer} ${a.sayYes}` : finalAnswer);
  }

  /** Reads a line aloud in voice mode, then listens again: a hands-free conversation. */
  function say(line: string) {
    setSpeaking(true);
    void speak(line, langRef.current, () => {
      setSpeaking(false);
      if (voiceRef.current && openRef.current) void listen();
    });
  }

  const patchAction = (turn: number, action: number, patch: Partial<Action>) =>
    update(turn, (x) => ({ actions: x.actions?.map((ac) => (ac.id === action ? { ...ac, ...patch } : ac)) }));

  async function run(turn: number, proposed: Action, confirmed: boolean) {
    pending.current = null;
    // the visitor may have edited the draft since it was proposed
    const ac = turnsRef.current.find((x) => x.id === turn)?.actions?.find((y) => y.id === proposed.id) ?? proposed;
    if (!confirmed) {
      patchAction(turn, ac.id, { state: "cancelled", outcome: a.cancelled });
      if (voiceRef.current) say(a.cancelled);
      return;
    }
    patchAction(turn, ac.id, { state: "running" });
    try {
      let outcome: string = a.done;
      let link: string | undefined;
      if (ac.kind === "tip") {
        const res = await publicApi<{ token: string; ref: string }>("/tips", {
          method: "POST",
          body: JSON.stringify({ newsroom: ac.newsroom, text: ac.text, url: ac.url || undefined, origin: ac.origin ?? "other" }),
        });
        rememberTip({ token: res.token, ref: res.ref, title: (ac.text ?? "").split("\n")[0].slice(0, 300) });
        outcome = a.sent(res.ref);
        link = `/suivi/${res.token}`;
      } else if (ws) {
        const res = await api<{ item_id: string; ref: string | null }>(`/workspaces/${ws}/copilot/act`, {
          method: "POST",
          body: JSON.stringify({ kind: ac.kind, item_id: ac.item_id, title: ac.title, body: ac.text, origin: ac.origin, url: ac.url, status: ac.status }),
        });
        link = `/w/${ws}/affirmations/${res.item_id}`;
        if (res.ref) outcome = `${a.done} ${res.ref}.`;
      }
      patchAction(turn, ac.id, { state: "done", outcome, link });
      if (voiceRef.current) say(outcome);
    } catch (err) {
      const note = err instanceof ApiError && err.status === 403 ? a.forbidden : err instanceof ApiError && err.status === 429 ? a.tooMany : a.actFailed;
      patchAction(turn, ac.id, { state: "failed", outcome: note });
    }
  }

  function setVoiceMode(on: boolean) {
    setVoice(on);
    voiceRef.current = on;
    stopSpeaking();
    setSpeaking(false);
    if (on && rec === "idle" && canRecord) void listen();
    if (!on && recorder.current?.state === "recording") recorder.current.stop();
  }

  /** The voice stage's one button: stop listening, cut the voice and speak, or start listening. */
  function stageAction() {
    if (rec === "listening") return stopRecording();
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
    }
    if (rec === "idle") void listen();
  }

  // A recorder only stops while recording (stop() on an idle one throws), so a press during the
  // mic's start-up does nothing.
  function stopRecording() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  function toggleDictation() {
    if (rec === "listening") return stopRecording();
    if (rec === "idle") void listen();
  }

  /** Records until the speaker pauses (1 s of silence after speech), then transcribes. */
  async function listen() {
    if (micBusy.current) return;
    micBusy.current = true;
    setNotice(null);
    setRec("listening"); // at once: the voice stage must not say "en pause" while the mic starts
    stopSpeaking();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      micBusy.current = false;
      setRec("idle");
      return setNotice(a.micDenied);
    }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported?.(m)) ?? "";
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    let heard = false;
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const started = performance.now();
    let loud = 0, quietSince = 0, frame = 0;
    const watch = () => {
      if (mr.state !== "recording") return;
      analyser.getFloatTimeDomainData(buf);
      const rms = Math.sqrt(buf.reduce((acc, v) => acc + v * v, 0) / buf.length);
      // the voice stage's bars follow the speaker's level, set straight on the element (no re-render)
      meter.current?.style.setProperty("--level", Math.min(1, rms * 14).toFixed(2));
      const now = performance.now();
      if (rms > 0.025) {
        loud += 1;
        quietSince = 0;
        if (loud > 6) heard = true; // ~100 ms of voice
      } else if (heard) {
        quietSince ||= now;
        if (now - quietSince > 1000) return mr.stop();
      }
      if (!heard && now - started > 8000) return mr.stop(); // nobody spoke
      if (now - started > 60_000) return mr.stop(); // about a minute at most
      frame = requestAnimationFrame(watch);
    };
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      cancelAnimationFrame(frame);
      micBusy.current = false;
      meter.current?.style.setProperty("--level", "0");
      stream.getTracks().forEach((tr) => tr.stop());
      void ctx.close();
      if (!heard) return setRec("idle");
      setRec("transcribing");
      try {
        const blob = new Blob(chunks, { type: (mr.mimeType || "audio/webm").split(";")[0] });
        const res = await fetch(`${API_URL}/api/v1/public/transcribe?lang=${langRef.current}`, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
        if (!res.ok) throw new Error(String(res.status));
        const { text: said } = (await res.json()) as { text: string };
        setRec("idle");
        if (!said.trim()) return;
        const waiting = pending.current;
        const words = said.trim().toLowerCase();
        if (voiceRef.current && waiting && (YES.test(words) || NO.test(words))) await run(waiting.turn, waiting.action, YES.test(words));
        else if (voiceRef.current) await ask(said);
        else setText((prev) => (prev ? `${prev} ${said}` : said));
      } catch {
        setNotice(a.dictationFailed);
        setRec("idle");
      }
    };
    recorder.current = mr;
    mr.start(250);
    frame = requestAnimationFrame(watch);
  }

  // Where the spoken conversation stands, said in the voice stage.
  const last = turns.at(-1);
  const phase = rec !== "idle" ? rec : last?.state === "thinking" ? "thinking" : speaking ? "speaking" : "idle";
  const awaiting = last?.actions?.some((ac) => ac.state === "pending");
  const hint =
    phase === "idle" && notice
      ? notice
      : phase === "listening" && awaiting
        ? a.sayYes
        : phase === "thinking" && last?.steps?.length
          ? `${last.steps.at(-1)}…`
          : a.stageHint[phase];

  return (
    <>
      {open && (
        <section className="assistant-panel" data-scope={scope} data-voice={voice || undefined} role="complementary" aria-labelledby="assistant-title">
          <header className="assistant-head">
            <h2 id="assistant-title">{a.title}</h2>
            {!!turns.length && (
              <button type="button" className="assistant-icon ml-auto" onClick={() => { stopSpeaking(); pending.current = null; setTurns([]); }} title={a.clear}>
                <RotateCcw className="size-4" aria-hidden />
                <span className="sr-only">{a.clear}</span>
              </button>
            )}
            {canRecord && (
              <button
                type="button"
                className={cn("assistant-voice-toggle", !turns.length && "ml-auto")}
                onClick={() => setVoiceMode(!voice)}
                aria-pressed={voice}
                title={voice ? a.voiceTurnOff : a.voiceTurnOn}
              >
                {voice ? <span className="assistant-dot" data-live={phase === "listening" || undefined} aria-hidden /> : <Mic className="size-4" aria-hidden />}
                {a.voiceShort}
                <span className="sr-only"> · {a.voiceMode}</span>
              </button>
            )}
            <button type="button" className="assistant-icon" onClick={() => setOpen(false)}>
              <X className="size-5" aria-hidden />
              <span className="sr-only">{a.close}</span>
            </button>
          </header>

          <div ref={log} className="assistant-log" aria-live="polite">
            <p className="assistant-lead">{ws ? a.leadDesk : a.leadPublic}</p>
            {turns.map((x) => {
              const used = x.cites?.filter((c) => citedNumbers(x.answer).has(c.n)) ?? [];
              return (
              <div key={x.id} className="space-y-2">
                <p className="assistant-q">{x.question}</p>
                <div className="assistant-a" data-state={x.state}>
                  {x.state === "thinking" && <p className="text-muted-foreground">{x.steps?.at(-1) ? `${x.steps.at(-1)}…` : a.thinking}</p>}
                  {x.answer && <p className="whitespace-pre-line">{renderCites(x.answer, x.cites)}</p>}
                  {x.note && <p className={cn(x.state === "error" && "text-verdict-false-ink")}>{x.note}</p>}
                  {used.some((c) => c.verdict) && (
                    <ul className="mt-2 space-y-1.5">
                      {used.map((c) =>
                        c.verdict && c.url ? (
                          <li key={c.n}>
                            <Link href={c.url as never} className="assistant-file">
                              <span className="tabular">[{c.n}]</span>
                              <span className="min-w-0 flex-1 truncate">{c.title}</span>
                              <VerdictChip verdict={c.verdict} />
                            </Link>
                          </li>
                        ) : null,
                      )}
                    </ul>
                  )}
                  {!!used.length && !used.some((c) => c.verdict) && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      {a.passages} : {used.map((c) => `[${c.n}] ${c.title}`).join(" · ")}
                    </p>
                  )}
                  {x.actions?.map((ac) => (
                    <ActionCard key={ac.id} action={ac} onRun={(ok) => void run(x.id, ac, ok)} onEdit={(patch) => patchAction(x.id, ac.id, patch)} />
                  ))}
                </div>
              </div>
              );
            })}
            {!turns.length && (
              <div className="flex flex-wrap gap-2">
                {(ws ? a.suggestionsDesk : a.suggestionsPublic).map((q) => (
                  <button key={q} type="button" className="assistant-chip" onClick={() => void ask(q)}>
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>

          {voice ? (
            <div className="assistant-stage" data-phase={phase}>
              <div className="assistant-stage-row">
                <div ref={meter} className="assistant-meter" aria-hidden>
                  {[0.45, 0.8, 1, 0.7, 0.5].map((k) => (
                    <i key={k} style={{ "--k": k } as React.CSSProperties} />
                  ))}
                </div>
                <div className="min-w-0 flex-1" role="status" aria-live="polite">
                  <p className="assistant-stage-label">{a.stage[phase]}</p>
                  <p className="assistant-stage-hint">{hint}</p>
                </div>
                <button
                  type="button"
                  className="assistant-stage-btn"
                  onClick={stageAction}
                  disabled={phase === "transcribing" || phase === "thinking"}
                >
                  {phase === "transcribing" || phase === "thinking" ? (
                    <LoaderCircle className="size-6 animate-spin" aria-hidden />
                  ) : phase === "listening" || phase === "speaking" ? (
                    <Square className="size-5" aria-hidden />
                  ) : (
                    <Mic className="size-6" aria-hidden />
                  )}
                  <span className="sr-only">
                    {phase === "listening" ? a.stageStop : phase === "speaking" ? a.stageCut : phase === "idle" ? a.stageListen : a.stageWait}
                  </span>
                </button>
              </div>
              <div className="assistant-stage-foot">
                <label className="sr-only" htmlFor="assistant-lang">{a.language}</label>
                <select id="assistant-lang" className="assistant-lang" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                  <option value="fr">FR</option>
                  <option value="mg">MG</option>
                </select>
                <button type="button" className="assistant-stage-link" onClick={() => setVoiceMode(false)}>
                  {a.typeInstead}
                </button>
              </div>
            </div>
          ) : (
          <form
            className="assistant-form"
            onSubmit={(e) => {
              e.preventDefault();
              void ask(text);
            }}
          >
            {notice && <p className="assistant-note w-full" role="alert">{notice}</p>}
            <div className="flex w-full items-center gap-2">
              <label className="sr-only" htmlFor="assistant-lang">{a.language}</label>
              <select id="assistant-lang" className="assistant-lang" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                <option value="fr">FR</option>
                <option value="mg">MG</option>
              </select>
              <span className="ml-auto text-sm text-muted-foreground">{rec === "listening" ? a.listening : rec === "transcribing" ? a.transcribing : ""}</span>
            </div>
            <div className="flex w-full items-end gap-2">
              <textarea
                ref={input}
                className="assistant-input"
                rows={2}
                value={text}
                maxLength={600}
                placeholder={a.placeholder}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void ask(text);
                  }
                }}
              />
              {canRecord && (
                <button type="button" className={cn("assistant-mic", rec === "listening" && "is-on")} onClick={toggleDictation} aria-pressed={rec === "listening"} disabled={rec === "transcribing"}>
                  {rec === "listening" ? <Square className="size-5" aria-hidden /> : <Mic className="size-5" aria-hidden />}
                  <span className="sr-only">{rec === "listening" ? a.stopDictate : a.dictate}</span>
                </button>
              )}
              <button type="submit" className="assistant-send" disabled={text.trim().length < 3}>
                <Send className="size-5" aria-hidden />
                <span className="sr-only">{a.send}</span>
              </button>
            </div>
          </form>
          )}
        </section>
      )}
    </>
  );
}

/** The numbers an answer cites, as [1], [1, 2] or 【1】: only those are listed under it. */
function citedNumbers(body: string) {
  const out = new Set<number>();
  for (const m of body.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]|【(\d+)/g)) for (const n of (m[1] ?? m[2]).split(",")) out.add(Number(n.trim()));
  return out;
}

// [n] (or 【n】) in an answer becomes a link to the cited verdict when there is one.
function renderCites(body: string, cites?: Cite[]) {
  return body.split(/(\[\d+\]|【\d+[^】]*】|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
    const n = Number(/^(?:\[(\d+)\]|【(\d+))/.exec(part)?.slice(1).find(Boolean));
    const c = n ? cites?.find((x) => x.n === n) : undefined;
    return c?.url?.startsWith("/") ? (
      <Link key={i} href={c.url as never} className="font-semibold underline underline-offset-2">
        [{n}]
      </Link>
    ) : (
      part
    );
  });
}

/** One proposed change: what it will do in plain words, and the two buttons. */
function ActionCard({ action: ac, onRun, onEdit }: { action: Action; onRun: (confirmed: boolean) => void; onEdit: (patch: Partial<Action>) => void }) {
  if (ac.kind === "navigate")
    return ac.href ? (
      <Link href={ac.href as never} className="assistant-file mt-2">
        <span className="min-w-0 flex-1 truncate">{a.opening(ac.label ?? ac.href)}</span>
        <span aria-hidden>→</span>
      </Link>
    ) : null;
  const what =
    ac.kind === "tip"
      ? null
      : ac.kind === "create_claim"
        ? a.actions.create_claim(ac.title ?? "")
        : ac.kind === "attach_link"
          ? a.actions.attach_link(ac.url ?? "", ac.ref ?? "")
          : ac.kind === "analyze"
            ? a.actions.analyze(ac.ref ?? "")
            : a.actions.set_status(ac.ref ?? "", ac.status ? t.status[ac.status] : "");
  return (
    <div className="assistant-action" data-state={ac.state}>
      <p className="assistant-action-head">{ac.kind === "tip" ? a.tipTitle : a.proposal}</p>
      {ac.kind === "tip" ? (
        <>
          <p className="text-sm text-muted-foreground">
            {ac.state === "pending" && (ac.newsrooms?.length ?? 0) > 1 ? (
              <select
                className="assistant-lang mr-1"
                aria-label={t.site.pub.report.newsroom}
                value={ac.newsroom}
                onChange={(e) => onEdit({ newsroom: e.target.value, newsroom_name: e.target.selectedOptions[0]?.text })}
              >
                {ac.newsrooms?.map((n) => (
                  <option key={n.slug} value={n.slug}>
                    {n.name}
                  </option>
                ))}
              </select>
            ) : (
              a.tipTo(ac.newsroom_name ?? "")
            )}{" "}
            · {a.tipFrom} {t.origins[ac.origin ?? "other"]}
          </p>
          {ac.state === "pending" ? (
            <textarea className="assistant-input mt-1.5 w-full" rows={3} maxLength={4000} aria-label={a.tipText} value={ac.text ?? ""} onChange={(e) => onEdit({ text: e.target.value })} />
          ) : (
            <blockquote className="assistant-quote">{ac.text}</blockquote>
          )}
          {ac.url && <p className="truncate text-sm">{ac.url}</p>}
        </>
      ) : (
        <p>{what}</p>
      )}
      {ac.state === "pending" || ac.state === "running" ? (
        <div className="mt-2 flex gap-2">
          <button type="button" className="assistant-confirm" disabled={ac.state === "running"} onClick={() => onRun(true)}>
            {ac.state === "running" ? a.working : ac.kind === "tip" ? a.sendTip : a.confirm}
          </button>
          <button type="button" className="assistant-cancel" disabled={ac.state === "running"} onClick={() => onRun(false)}>
            {a.cancel}
          </button>
        </div>
      ) : (
        <p className={cn("mt-1 text-sm font-medium", ac.state === "failed" && "text-verdict-false-ink")} role="status">
          {ac.outcome}{" "}
          {ac.link && ac.state === "done" && (
            <Link href={ac.link as never} className="underline underline-offset-4">
              {ac.kind === "tip" ? a.follow : a.openIt} →
            </Link>
          )}
        </p>
      )}
    </div>
  );
}
