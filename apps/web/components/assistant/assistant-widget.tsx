"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AudioLines, Mic, MessageCircle, Send, Square, Volume2, VolumeX, X } from "lucide-react";
import { VerdictChip } from "@/components/site/fragments";
import { API_URL, ApiError } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, publicApi } from "@/lib/public-api";
import { postStream } from "@/lib/sse";
import { cn } from "@/lib/utils";

const a = t.assistant;
type Lang = "fr" | "mg";
type Passage = { n: number; title: string };
type Turn = {
  id: number;
  question: string;
  answer: string;
  state: "thinking" | "answering" | "done" | "error";
  verdicts?: PublicVerdict[];
  passages?: Passage[];
  note?: string;
  unchecked?: boolean;
};

const plain = (s: string) => s.replace(/\[\d+\]|【[^】]*】|\*\*/g, "").replace(/\s+/g, " ").trim();

let voiceMissing = false; // the API has no ElevenLabs key: stop asking for it
let playing: HTMLAudioElement | null = null;

/** Reads an answer aloud: the ElevenLabs voice when the API has one, otherwise the browser's own. */
async function speak(text: string, lang: Lang, onEnd: () => void) {
  stopSpeaking();
  if (!voiceMissing) {
    try {
      const res = await fetch(`${API_URL}/api/v1/public/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 900), lang }),
      });
      if (res.status === 501) voiceMissing = true;
      else if (res.ok) {
        const url = URL.createObjectURL(await res.blob());
        playing = new Audio(url);
        playing.onended = playing.onerror = () => {
          URL.revokeObjectURL(url);
          playing = null;
          onEnd();
        };
        await playing.play();
        return;
      }
    } catch {
      // fall through to the browser's voice
    }
  }
  if (!("speechSynthesis" in window)) return onEnd();
  const u = new SpeechSynthesisUtterance(plain(text));
  const voices = speechSynthesis.getVoices();
  u.voice = voices.find((v) => v.lang.toLowerCase().startsWith(lang)) ?? voices.find((v) => v.lang.toLowerCase().startsWith("fr")) ?? null;
  u.lang = u.voice?.lang ?? "fr-FR";
  u.onend = u.onerror = () => onEnd();
  speechSynthesis.speak(u);
}

function stopSpeaking() {
  playing?.pause();
  playing = null;
  if (typeof window !== "undefined" && "speechSynthesis" in window) speechSynthesis.cancel();
}

/**
 * The floating assistant on every page. Signed-out (or outside a workspace) it answers from published
 * verdicts only; inside a workspace it asks the desk's own sources. Questions can be typed or dictated
 * (French or Malagasy, Whisper), and in voice mode answers are read aloud.
 */
export function AssistantWidget({ scope = "public" }: { scope?: "public" | "desk" }) {
  const params = useParams<{ ws?: string }>();
  const ws = scope === "desk" ? params?.ws : undefined;
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [lang, setLang] = useState<Lang>("fr");
  const [voice, setVoice] = useState(false);
  const [rec, setRec] = useState<"idle" | "listening" | "transcribing">("idle");
  const [speaking, setSpeaking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const seq = useRef(0);
  const voiceRef = useRef(voice);
  const openRef = useRef(open);
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
  }, [turns]);
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [open]);
  useEffect(() => () => stopSpeaking(), []);

  const update = (id: number, patch: (x: Turn) => Partial<Turn>) => setTurns((all) => all.map((x) => (x.id === id ? { ...x, ...patch(x) } : x)));

  async function ask(question: string) {
    const q = question.trim();
    if (q.length < 3) return;
    const id = ++seq.current;
    setTurns((all) => [...all, { id, question: q, answer: "", state: "thinking" }]);
    setText("");
    let finalAnswer = "";
    try {
      if (ws) {
        await postStream(`/workspaces/${ws}/ask`, { question: q, k: 4 }, (event, data) => {
          if (event === "citations") update(id, () => ({ passages: data as Passage[], state: "answering" }));
          else if (event === "delta") update(id, (x) => ((finalAnswer = x.answer + (data as { text: string }).text), { answer: finalAnswer }));
          else if (event === "error") update(id, () => ({ state: "error", note: a.failed }));
        });
        update(id, (x) => (x.state === "error" ? {} : { state: "done" }));
      } else {
        const res = await publicApi<{ answer: string | null; verdicts: PublicVerdict[]; checked: boolean }>("/ask", {
          method: "POST",
          body: JSON.stringify({ question: q.slice(0, 600) }),
        });
        finalAnswer = res.answer ?? (res.checked ? a.busy : a.notChecked);
        update(id, () => ({ answer: res.answer ?? "", verdicts: res.verdicts, state: "done", unchecked: !res.checked, note: res.answer ? undefined : res.checked ? a.busy : a.notChecked }));
      }
      if (voiceRef.current && finalAnswer) {
        setSpeaking(true);
        void speak(finalAnswer, lang, () => {
          setSpeaking(false);
          // a conversation: once the answer is read, the assistant listens again
          if (voiceRef.current && openRef.current) void listen();
        });
      }
    } catch (err) {
      update(id, () => ({ state: "error", note: err instanceof ApiError && err.status === 429 ? a.tooMany : a.failed }));
    }
  }

  function toggleDictation() {
    if (rec === "listening") return recorder.current?.stop();
    if (rec === "idle") void listen();
  }

  /** Records until the speaker pauses (about 1.2 s of silence after speech), then transcribes. */
  async function listen() {
    setNotice(null);
    stopSpeaking();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
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
      const now = performance.now();
      if (rms > 0.025) {
        loud += 1;
        quietSince = 0;
        if (loud > 6) heard = true; // ~100 ms of voice
      } else if (heard) {
        quietSince ||= now;
        if (now - quietSince > 1200) return mr.stop();
      }
      if (!heard && now - started > 8000) return mr.stop(); // nobody spoke
      if (now - started > 60_000) return mr.stop(); // about a minute at most
      frame = requestAnimationFrame(watch);
    };
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((tr) => tr.stop());
      void ctx.close();
      if (!heard) return setRec("idle");
      setRec("transcribing");
      try {
        const blob = new Blob(chunks, { type: (mr.mimeType || "audio/webm").split(";")[0] });
        const res = await fetch(`${API_URL}/api/v1/public/transcribe?lang=${lang}`, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
        if (!res.ok) throw new Error(String(res.status));
        const { text: said } = (await res.json()) as { text: string };
        setRec("idle");
        if (!said.trim()) return;
        if (voiceRef.current) await ask(said);
        else setText((prev) => (prev ? `${prev} ${said}` : said));
      } catch {
        setNotice(a.dictationFailed);
        setRec("idle");
      }
    };
    recorder.current = mr;
    mr.start(250);
    setRec("listening");
    frame = requestAnimationFrame(watch);
  }

  return (
    <div className="assistant" data-scope={scope}>
      {open && (
        <section className="assistant-panel" role="dialog" aria-modal="false" aria-labelledby="assistant-title">
          <header className="assistant-head">
            <AudioLines className="size-5" aria-hidden />
            <h2 id="assistant-title">{a.title}</h2>
            <button type="button" className="assistant-icon ml-auto" onClick={() => {
                const on = !voice;
                setVoice(on);
                voiceRef.current = on;
                stopSpeaking();
                if (on && rec === "idle" && canRecord) void listen();
                if (!on && recorder.current?.state === "recording") recorder.current.stop();
              }} aria-pressed={voice} title={a.voiceMode}>
              {voice ? <Volume2 className="size-5" aria-hidden /> : <VolumeX className="size-5" aria-hidden />}
              <span className="sr-only">{a.voiceMode}</span>
            </button>
            <button type="button" className="assistant-icon" onClick={() => setOpen(false)}>
              <X className="size-5" aria-hidden />
              <span className="sr-only">{a.close}</span>
            </button>
          </header>

          <div ref={log} className="assistant-log" aria-live="polite">
            <p className="assistant-lead">{ws ? a.leadDesk : a.leadPublic}</p>
            {voice && <p className="assistant-note">{a.voiceOn}</p>}
            {turns.map((x) => (
              <div key={x.id} className="space-y-2">
                <p className="assistant-q">{x.question}</p>
                <div className="assistant-a">
                  {x.state === "thinking" && <p className="text-muted-foreground">{a.thinking}</p>}
                  {x.answer && <p className="whitespace-pre-line">{renderCites(x.answer, x.verdicts)}</p>}
                  {x.note && <p className={cn(x.state === "error" && "text-verdict-false-ink")}>{x.note}</p>}
                  {!!x.verdicts?.length && (
                    <ul className="mt-2 space-y-1.5">
                      {x.verdicts.map((v, i) => (
                        <li key={v.id}>
                          <Link href={`/verifies/${v.id}`} className="assistant-file">
                            <span className="tabular">[{i + 1}]</span>
                            <span className="min-w-0 flex-1 truncate">{v.title}</span>
                            <VerdictChip verdict={v.verdict} />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                  {!!x.passages?.length && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      {a.passages} : {x.passages.map((p) => `[${p.n}] ${p.title}`).join(" · ")}
                    </p>
                  )}
                  {x.unchecked && (
                    <Link href={`/signaler?texte=${encodeURIComponent(x.question)}`} className="mt-2 inline-block font-medium underline underline-offset-4">
                      {a.report} →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>

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
              {speaking && (
                <button type="button" className="assistant-icon" onClick={() => { stopSpeaking(); setSpeaking(false); }}>
                  <Square className="size-4" aria-hidden />
                  <span className="sr-only">{a.stopSpeaking}</span>
                </button>
              )}
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
        </section>
      )}
      <button type="button" className="assistant-fab" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? a.close : a.open}>
        {open ? <X className="size-6" aria-hidden /> : <MessageCircle className="size-6" aria-hidden />}
      </button>
    </div>
  );
}

// [n] (or 【n】) in an answer becomes a link to the cited file when there is one.
function renderCites(body: string, files?: PublicVerdict[]) {
  return body.split(/(\[\d+\]|【\d+[^】]*】|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
    const n = Number(/^(?:\[(\d+)\]|【(\d+))/.exec(part)?.slice(1).find(Boolean));
    const v = n && files?.[n - 1];
    return v ? (
      <Link key={i} href={`/verifies/${v.id}`} className="font-semibold underline underline-offset-2">
        [{n}]
      </Link>
    ) : (
      part
    );
  });
}
