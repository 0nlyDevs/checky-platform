import * as THREE from "three";
import type { ClipTone, HeroClip } from "../content/hero";

/**
 * One texture per hero clip. Until a real file is set (`src`) or while it
 * loads, the texture is a drawn placeholder card, so both heroes can be built
 * and reviewed before the footage exists.
 */
export interface ClipSource {
  clip: HeroClip;
  /** Current texture: the placeholder, then the video once it has frames. */
  texture: THREE.Texture;
  aspect: number;
  video: HTMLVideoElement | null;
  /** True once something real can be shown (always true for placeholders). */
  ready: boolean;
  play(): void;
  pause(): void;
  dispose(): void;
}

/** Hue range, saturation and lightness of each tone; each clip picks its own hue in the range. */
const TONE: Record<ClipTone, { hue: [number, number]; sat: number; light: number; ink: string }> = {
  cool: { hue: [185, 228], sat: 46, light: 30, ink: "rgba(236,243,248,0.85)" },
  warm: { hue: [8, 38], sat: 58, light: 32, ink: "rgba(250,239,229,0.86)" },
  mono: { hue: [30, 40], sat: 4, light: 26, ink: "rgba(240,240,240,0.82)" },
  bright: { hue: [38, 62], sat: 40, light: 70, ink: "rgba(30,27,22,0.8)" },
};

const MONO = '"Geist Mono Variable", "JetBrains Mono Variable", ui-monospace, Menlo, monospace';

function hash(n: number) {
  const t = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return t - Math.floor(t);
}

export function drawPlaceholder(ctx: CanvasRenderingContext2D, w: number, h: number, clip: HeroClip, index: number) {
  const tone = TONE[clip.tones[0] ?? "mono"];
  const hue = tone.hue[0] + (tone.hue[1] - tone.hue[0]) * hash(index + 3);
  const a = `hsl(${hue} ${tone.sat}% ${tone.light + 8}%)`;
  const b = `hsl(${hue + 12} ${tone.sat * 0.8}% ${Math.max(5, tone.light - 22)}%)`;
  const glowCol = (alpha: number) => `hsl(${hue - 10} ${Math.min(90, tone.sat + 25)}% ${Math.min(88, tone.light + 34)}% / ${alpha})`;
  const bg = ctx.createLinearGradient(0, 0, w, h);
  bg.addColorStop(0, a);
  bg.addColorStop(1, b);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  // soft light, placed per clip so the cards do not all look alike
  const gx = (0.2 + 0.6 * hash(index + 1)) * w;
  const gy = (0.15 + 0.4 * hash(index + 7)) * h;
  const glow = ctx.createRadialGradient(gx, gy, 0, gx, gy, w * 0.7);
  glow.addColorStop(0, glowCol(0.55));
  glow.addColorStop(0.45, glowCol(0.14));
  glow.addColorStop(1, glowCol(0));
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, w, h);

  // a horizon band, so the card reads as footage rather than a flat swatch
  const hy = (0.55 + 0.2 * hash(index + 13)) * h;
  const band = ctx.createLinearGradient(0, hy - h * 0.12, 0, hy + h * 0.3);
  band.addColorStop(0, "rgba(0,0,0,0)");
  band.addColorStop(1, "rgba(0,0,0,0.38)");
  ctx.fillStyle = band;
  ctx.fillRect(0, hy - h * 0.12, w, h);

  // play mark
  const r = h * 0.1;
  ctx.strokeStyle = tone.ink;
  ctx.lineWidth = Math.max(2, h * 0.008);
  ctx.beginPath();
  ctx.arc(w / 2, h / 2, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = tone.ink;
  ctx.beginPath();
  ctx.moveTo(w / 2 - r * 0.32, h / 2 - r * 0.45);
  ctx.lineTo(w / 2 + r * 0.5, h / 2);
  ctx.lineTo(w / 2 - r * 0.32, h / 2 + r * 0.45);
  ctx.closePath();
  ctx.fill();

  // label
  ctx.font = `500 ${Math.round(h * 0.06)}px ${MONO}`;
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.fillText(clip.label.toUpperCase(), w * 0.05, h * 0.9);
  ctx.textAlign = "right";
  ctx.globalAlpha = 0.6;
  ctx.fillText("16:9", w * 0.95, h * 0.9);
  ctx.globalAlpha = 1;
}

interface Options {
  colorSpace: THREE.ColorSpace;
}

export function createClipSources(clips: HeroClip[], { colorSpace }: Options): ClipSource[] {
  return clips.map((clip, index) => {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 360;
    const ctx = canvas.getContext("2d")!;
    drawPlaceholder(ctx, 640, 360, clip, index);
    const still = new THREE.CanvasTexture(canvas);
    still.colorSpace = colorSpace;
    still.minFilter = THREE.LinearFilter;
    still.magFilter = THREE.LinearFilter;
    still.generateMipmaps = false;

    // Redraw once the mono face has loaded, so the label uses it.
    document.fonts?.ready.then(() => {
      drawPlaceholder(ctx, 640, 360, clip, index);
      still.needsUpdate = true;
    });

    const source: ClipSource = {
      clip,
      texture: still,
      aspect: 16 / 9,
      video: null,
      ready: true,
      play() {
        this.video?.play().catch(() => {});
      },
      pause() {
        if (this.video && this.video.readyState >= 2) this.video.pause();
      },
      dispose() {
        still.dispose();
        if (this.texture !== still) this.texture.dispose();
        if (this.video) {
          this.video.pause();
          this.video.removeAttribute("src");
          this.video.load();
        }
      },
    };

    if (clip.src) {
      const video = document.createElement("video");
      video.crossOrigin = "anonymous";
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = "auto";
      video.disableRemotePlayback = true;
      video.src = clip.src;
      source.video = video;
      video.addEventListener(
        "loadeddata",
        () => {
          const tex = new THREE.VideoTexture(video);
          tex.colorSpace = colorSpace;
          tex.minFilter = THREE.LinearFilter;
          tex.magFilter = THREE.LinearFilter;
          source.texture = tex;
          source.aspect = video.videoWidth / video.videoHeight || 16 / 9;
        },
        { once: true },
      );
      // A missing file keeps the placeholder.
      video.addEventListener("error", () => {}, { once: true });
    }
    return source;
  });
}
