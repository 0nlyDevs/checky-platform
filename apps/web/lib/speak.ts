import { API_URL } from "@/lib/api";

export type Lang = "fr" | "mg";

const plain = (s: string) => s.replace(/\[\d+\]|【[^】]*】|\*\*/g, "").replace(/\s+/g, " ").trim();

let voiceMissing = false; // the API has no ElevenLabs key: stop asking for it
let playing: HTMLAudioElement | null = null;

/** Reads an answer aloud: the ElevenLabs voice when the API has one, otherwise the browser's own. */
export async function speak(text: string, lang: Lang, onEnd: () => void) {
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

export function stopSpeaking() {
  playing?.pause();
  playing = null;
  if (typeof window !== "undefined" && "speechSynthesis" in window) speechSynthesis.cancel();
}
