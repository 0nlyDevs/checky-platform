"use client";

import jsQR from "jsqr";
import { api } from "@/lib/api";
import { uploadFile, type Source } from "@/lib/upload";

/* The Shape Detection API: native QR reading on Android Chrome; text reading behind a flag in some
   Chromium builds. Neither is in the DOM types yet. */
type Detected = { rawValue: string };
type Detector = { detect(source: CanvasImageSource | ImageBitmap): Promise<Detected[]> };
type DetectorClass = { new (options?: { formats: string[] }): Detector; getSupportedFormats?: () => Promise<string[]> };
const global = () => globalThis as unknown as { BarcodeDetector?: DetectorClass; TextDetector?: DetectorClass };

let native: Promise<Detector | null> | null = null;
/** The native QR reader when this browser has one, else null (jsQR decodes the frames instead). */
export function nativeQr(): Promise<Detector | null> {
  native ??= (async () => {
    const Barcode = global().BarcodeDetector;
    if (!Barcode) return null;
    try {
      const formats = (await Barcode.getSupportedFormats?.()) ?? ["qr_code"];
      return formats.includes("qr_code") ? new Barcode({ formats: ["qr_code"] }) : null;
    } catch {
      return null;
    }
  })();
  return native;
}

const canvas = () => document.createElement("canvas");

/** Reads a QR in a video frame or a picture: natively when possible, otherwise with jsQR. */
export async function readQr(source: HTMLVideoElement | ImageBitmap, scratch: HTMLCanvasElement = canvas()): Promise<string | null> {
  const detector = await nativeQr();
  if (detector) {
    try {
      const found = await detector.detect(source);
      if (found[0]?.rawValue) return found[0].rawValue;
    } catch {
      // fall through to jsQR
    }
  }
  const width = source instanceof HTMLVideoElement ? source.videoWidth : source.width;
  const height = source instanceof HTMLVideoElement ? source.videoHeight : source.height;
  if (!width || !height) return null;
  // Big photos are scaled down: jsQR is fast enough at ~1000 px and a QR stays readable.
  const scale = Math.min(1, 1000 / Math.max(width, height));
  scratch.width = Math.round(width * scale);
  scratch.height = Math.round(height * scale);
  const ctx = scratch.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(source, 0, 0, scratch.width, scratch.height);
  const pixels = ctx.getImageData(0, 0, scratch.width, scratch.height);
  return jsQR(pixels.data, pixels.width, pixels.height, { inversionAttempts: "attemptBoth" })?.data ?? null;
}

/** The text of a printed page, read on the device where the browser can (TextDetector); null otherwise. */
export async function readText(picture: ImageBitmap): Promise<string | null> {
  const Text = global().TextDetector;
  if (!Text) return null;
  try {
    const lines = await new Text().detect(picture);
    const text = lines
      .map((l) => l.rawValue)
      .join("\n")
      .trim();
    return text || null;
  } catch {
    return null;
  }
}

export const canReadText = () => typeof globalThis !== "undefined" && "TextDetector" in globalThis;

/** Sends a photo to the newsroom's sources and waits until it is read, for Vérifier to check it. */
export async function sendPhoto(ws: string, file: File | Blob, name = "photo.jpg"): Promise<string> {
  const asFile = file instanceof File ? file : new File([file], name, { type: file.type || "image/jpeg" });
  let source: Source = await uploadFile(ws, asFile, undefined, () => {});
  for (let i = 0; i < 30 && source.status !== "ready" && source.status !== "failed"; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    source = await api<Source>(`/workspaces/${ws}/sources/${source.id}`);
  }
  if (source.status !== "ready") throw new Error(`source ${source.status}`);
  return source.id;
}
