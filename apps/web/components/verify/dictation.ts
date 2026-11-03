"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Record French speech and get its text back. Spoken Malagasy stays with a person. */
export function useDictation(onText: (text: string) => void) {
  const v = useT().verify;
  const [state, setState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  // Known only in the browser: decided after mount so the server and the first render agree.
  const [can, setCan] = useState(false);
  useEffect(() => {
    requestAnimationFrame(() => setCan("MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia));
  }, []);

  async function toggle() {
    if (state === "recording") return rec.current?.stop();
    if (state !== "idle") return;
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      return setError(v.micDenied);
    }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported?.(m)) ?? "";
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop());
      setState("transcribing");
      try {
        const blob = new Blob(chunks, {
          type: (mr.mimeType || "audio/webm").split(";")[0],
        });
        const res = await fetch(`${API_URL}/api/v1/public/transcribe?lang=fr`, {
          method: "POST",
          headers: { "Content-Type": blob.type },
          body: blob,
        });
        if (!res.ok) throw new Error(String(res.status));
        const { text } = (await res.json()) as { text: string };
        if (text.trim()) onText(text.trim());
      } catch {
        setError(v.dictationFailed);
      } finally {
        setState("idle");
      }
    };
    rec.current = mr;
    mr.start(250);
    setState("recording");
  }
  return { state, error, can, toggle };
}
