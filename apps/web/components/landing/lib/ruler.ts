/**
 * Shared state and tuning of the right-hand section ruler (page position rail
 * plus the flying section headings). Mirrors the reference ruler's defaults.
 */

/** Height the reference reserves for its top bar; the heading stack starts below it. */
export const NAV_H = 48;

export const LAYOUT = {
  edgePad: 12,
  railW: 60,
  minorPct: 1,
  labelPct: 5,
  /** Viewport-height % from the top where a riding word flips into the top stack. */
  thresholdPct: 12,
  headingPx: 34,
  ridingPx: 20,
  queuePx: 16,
  topPad: 28,
  currentGap: 26,
  queueSlot: 20,
  queuePad: 36,
  textPad: 0,
};

export const MOTION = {
  flipZone: 200,
  detachZone: 240,
  stagger: 0.16,
  arc: 28,
  jumpDur: 1.25,
  snapDelay: 400,
  snapDur: 0.7,
  introDur: 1,
  introStagger: 0.01,
  velRadius: 180,
  velMax: 0.6,
  zoomInDelay: 150,
  zoomOutDelay: 150,
  zoomLerp: 10,
  dragLerp: 0.18,
  heroLead: 100,
  heroZone: 320,
};

export const LOOK = {
  minorAlpha: 0.4,
  majorAlpha: 0.8,
  labelAlpha: 0.5,
  minorLen: 10,
  majorLen: 20,
  ghostAlpha: 1,
  ghostThick: 3,
  queueAlpha: 0.35,
  yieldPad: 24,
  needleFadePct: 3,
  bracketAlpha: 0.1,
  mapAlpha: 0.85,
  poolAlpha: 1,
  frostSolid: 40,
  frostGamma: 2.2,
  poolPad: 64,
};

/** Heading type: the hero wordmark morphs from its own weight/stretch to these. */
export const DISPLAY_WEIGHT = 800;
export const DISPLAY_STRETCH = 100;
export const WORDMARK_WEIGHT = 800;
export const WORDMARK_STRETCH = 100;

export const clamp01 = (e: number) => Math.max(0, Math.min(1, e));
export const easeInOutCubic = (e: number) => (e < 0.5 ? 4 * e * e * e : 1 - Math.pow(-2 * e + 2, 3) / 2);
export const easeOutExpo = (e: number) => (e >= 1 ? 1 : 1 - Math.pow(2, -10 * e));

export interface Metrics {
  /** Advance of each letter, per 1px of font size. */
  adv: number[];
  cum: number[];
  total: number;
}

/**
 * The hero wordmark, published by HeroWordmark so the ruler can fly its own
 * letters into the top heading slot. Positions are live viewport centres at
 * rest (the hero stage is pinned, so they are read every frame).
 */
export const heroWordmark = {
  ready: false,
  forming: true,
  /** The real hero letters; hidden while their copies fly. */
  els: [] as HTMLElement[],
  word: "",
  fontPx: 0,
  /** Rest centres, in viewport px, of each letter. */
  restX: [] as number[],
  restY: [] as number[],
  /** Document y of the letters' centre line in the unpinned flow. */
  docCenterY: 0,
  /** Reads restX/restY for the current frame. */
  read: () => {},
};

/** Spans of the rail covered by a riding heading; tick labels fade under them. */
export const railOccupancy = { spans: [] as { top: number; bottom: number; k: number }[] };

/** Hover zoom of the ruler into a full-page map. */
export const rulerZoom = { target: 0, p: 0, dragging: false };

/** Whether the animated ruler runs here (desktop, fine pointer, motion allowed). */
export function rulerFlies() {
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)) return false;
  return (
    window.matchMedia("(pointer: fine) and (hover: hover) and (min-width: 1024px)").matches &&
    window.matchMedia("(prefers-reduced-motion: no-preference)").matches
  );
}

export function rulerMap(vh: number, edgePad: number) {
  const base = NAV_H + edgePad;
  return {
    base,
    span: Math.max(1, vh - NAV_H - 2 * edgePad),
    drift: (f: number) => base - f * (NAV_H + 2 * edgePad),
  };
}

/** Per-letter advances of `label` in the heading font, per 1px of font size. */
export function measureLabels(labels: string[], className: string) {
  const box = document.createElement("div");
  box.className = className;
  box.style.cssText = "position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;font-size:100px;line-height:1;";
  // Inside the landing, where the heading font is set (styles are scoped to `.landing`).
  (document.querySelector(".landing") ?? document.body).appendChild(box);
  const out: Record<string, Metrics> = {};
  for (const label of labels) {
    box.textContent = "";
    const adv = label
      .split("")
      .map((ch) => {
        const s = document.createElement("span");
        s.textContent = ch;
        box.appendChild(s);
        return s;
      })
      .map((s) => s.getBoundingClientRect().width / 100);
    const cum: number[] = [];
    let total = 0;
    for (const a of adv) {
      cum.push(total);
      total += a;
    }
    out[label] = { adv, cum, total };
  }
  box.remove();
  return out;
}
