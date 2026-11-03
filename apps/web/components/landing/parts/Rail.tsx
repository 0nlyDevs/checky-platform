import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { SECTIONS } from "../content/site";
import { gsap, ScrollTrigger, useGSAP, getLenis } from "../lib/motion";
import { INTRO, introClock } from "../lib/intro";
import {
  DISPLAY_STRETCH,
  DISPLAY_WEIGHT,
  LAYOUT as L,
  LOOK,
  MOTION as M,
  NAV_H,
  WORDMARK_STRETCH,
  WORDMARK_WEIGHT,
  clamp01,
  easeInOutCubic,
  easeOutExpo,
  heroWordmark,
  measureLabels,
  railOccupancy,
  rulerMap,
  rulerZoom,
  type Metrics,
} from "../lib/ruler";

type Mode = "full" | "static" | null;
interface Geom {
  docH: number;
  vh: number;
  vw: number;
}
interface Section {
  id: string;
  label: string;
  anchor: number;
  bottom: number;
  isHero: boolean;
}
interface Tick {
  pct: number;
  docY: number;
  major: boolean;
  alpha: number;
}
interface Pose {
  x: number;
  y: number;
  rot: number;
  scale: number;
  alpha: number;
}

const HERO_ID = "checky";
const LETTER_CLASS = "ruler-letter";
const LABELS = SECTIONS.map((s) => ({ id: s.id, label: s.label.toUpperCase() }));

/** Frost mask of the rail: solid at the outer edge, eased feather toward the page. */
function frostMask(solid: number, gamma: number) {
  const stops = [`black ${solid.toFixed(0)}%`];
  for (let k = 1; k < 8; k++) {
    const i = k / 8;
    stops.push(`rgba(0,0,0,${Math.pow(1 - i, gamma).toFixed(3)}) ${(solid + i * (100 - solid)).toFixed(1)}%`);
  }
  stops.push("transparent 100%");
  return `linear-gradient(to left, ${stops.join(", ")})`;
}

const poolMask = (at: string) =>
  `radial-gradient(100% 100% at 100% ${at}, black 38%, rgba(0,0,0,0.82) 56%, rgba(0,0,0,0.48) 72%, rgba(0,0,0,0.2) 86%, rgba(0,0,0,0.05) 94%, transparent 97%)`;

function useMode(): Mode {
  const [mode, setMode] = useState<Mode>(null);
  useEffect(() => {
    const mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    const fine = window.matchMedia("(pointer: fine) and (hover: hover) and (min-width: 1024px)");
    const calm = window.matchMedia("(prefers-reduced-motion: no-preference)");
    const sync = () => setMode(!mobile && fine.matches ? (calm.matches ? "full" : "static") : null);
    sync();
    fine.addEventListener("change", sync);
    calm.addEventListener("change", sync);
    return () => {
      fine.removeEventListener("change", sync);
      calm.removeEventListener("change", sync);
    };
  }, []);
  return mode;
}

function scrollToY(y: number, duration: number) {
  const lenis = getLenis();
  if (lenis) lenis.scrollTo(y, { duration, easing: easeOutExpo });
  else window.scrollTo({ top: y });
}

/**
 * Right-hand page ruler: ticks that travel with the document, a needle with a
 * rolling percentage, and the section headings. A heading waits in the bottom
 * queue, rides the rail beside its section, then flips letter by letter into
 * the top stack. On the galaxy page the hero wordmark itself flies into the
 * first slot. Hovering the rail zooms it into a full-page map.
 */
export function Rail({ ready, heroWord }: { ready: boolean; heroWord: boolean }) {
  const mode = useMode();
  const [geom, setGeom] = useState<Geom>({ docH: 0, vh: 0, vw: 0 });
  const [sections, setSections] = useState<Section[]>([]);
  const [metrics, setMetrics] = useState<Record<string, Metrics> | null>(null);

  const railRef = useRef<HTMLDivElement>(null);
  const tickTrack = useRef<HTMLDivElement>(null);
  const needle = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLSpanElement>(null);
  const bracket = useRef<HTMLDivElement>(null);
  const ghostBox = useRef<HTMLDivElement>(null);
  const ghostLine = useRef<HTMLDivElement>(null);
  const tickEls = useRef<(HTMLSpanElement | null)[]>([]);
  const tickRows = useRef<(HTMLDivElement | null)[]>([]);
  const tickLabels = useRef<(HTMLSpanElement | null)[]>([]);
  const digitCols = useRef<(HTMLSpanElement | null)[]>([]);
  const topPool = useRef<HTMLDivElement>(null);
  const bottomPool = useRef<HTMLDivElement>(null);
  const heads = useRef<{ letters: (HTMLSpanElement | null)[]; hit: HTMLAnchorElement | null }[]>([]);
  const hover = useRef(-1);

  const st = useRef({
    vel: 0,
    lastY: 0,
    introDone: false,
    prevDigits: [-1, -1, -1],
    prevPct: -1,
    readoutAbove: false,
    geom: { docH: 0, vh: 0, vw: 0 } as Geom,
    zoomIntent: false,
    zoomTimer: 0,
    zoomWrote: false,
    ghostActive: false,
    ghostY: 0,
    dragStartY: 0,
    dragMoved: 0,
    // headings
    snapSince: null as number | null,
    snapping: false,
    armed: true,
    jumping: false,
  });
  useEffect(() => {
    st.current.geom = geom;
  }, [geom]);

  const hoverK = useMemo(() => new Float32Array(LABELS.length), []);
  const flashAt = useMemo(() => new Float64Array(LABELS.length), []);

  // html flags: hide the native scrollbar while the ruler stands in for it.
  useEffect(() => {
    if (!mode) return;
    const html = document.documentElement;
    html.dataset.ruler = mode === "full" ? "on" : "static";
    return () => {
      delete html.dataset.ruler;
    };
  }, [mode]);

  useEffect(() => {
    if (!mode) return;
    const read = () => {
      const g = { docH: document.documentElement.scrollHeight, vh: window.innerHeight, vw: window.innerWidth };
      setGeom((p) => (p.docH === g.docH && p.vh === g.vh && p.vw === g.vw ? p : g));
    };
    read();
    const ro = new ResizeObserver(read);
    ro.observe(document.body);
    window.addEventListener("resize", read);
    document.fonts?.ready.then(read).catch(() => {});
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", read);
    };
  }, [mode]);

  // Section anchors, read once layout has settled (next frame).
  useEffect(() => {
    if (!mode || !geom.docH) return;
    const id = requestAnimationFrame(() => {
      const out: Section[] = [];
      for (const s of LABELS) {
        const el = document.getElementById(s.id);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        out.push({
          id: s.id,
          label: s.label,
          anchor: r.top + window.scrollY,
          bottom: r.bottom + window.scrollY,
          isHero: heroWord && s.id === HERO_ID,
        });
      }
      setSections(out);
    });
    return () => cancelAnimationFrame(id);
  }, [mode, geom, heroWord]);

  useEffect(() => {
    if (mode !== "full") return;
    let dead = false;
    const run = () => {
      if (!dead)
        setMetrics(
          measureLabels(
            LABELS.map((s) => s.label),
            LETTER_CLASS,
          ),
        );
    };
    const f = document.fonts?.ready;
    if (f) f.then(run).catch(run);
    else run();
    return () => {
      dead = true;
    };
  }, [mode]);

  const ticks = useMemo<Tick[]>(() => {
    if (!mode || !geom.docH) return [];
    const out: Tick[] = [];
    for (let p = 0; p <= 100 + 1e-6; p += L.minorPct) {
      const pct = Math.round(100 * p) / 100;
      const major = Math.abs(pct % L.labelPct) < 1e-6;
      out.push({ pct, docY: (pct / 100) * geom.docH, major, alpha: major ? LOOK.majorAlpha : LOOK.minorAlpha });
    }
    return out;
  }, [mode, geom.docH]);
  useEffect(() => {
    tickEls.current.length = ticks.length;
    tickRows.current.length = ticks.length;
    tickLabels.current.length = ticks.length;
  }, [ticks]);

  // Tick intro: they draw in from the rail edge once the hero lines appear.
  useEffect(() => {
    if (mode !== "full" || !ticks.length) return;
    const els = tickEls.current.filter((e): e is HTMLSpanElement => !!e);
    if (!els.length) return;
    if (introClock.done || st.current.introDone) {
      gsap.set(els, { scaleX: 1, opacity: (i) => ticks[i]?.alpha ?? 0.3 });
      st.current.introDone = true;
      return;
    }
    gsap.set(els, { scaleX: 0, opacity: 0 });
    if (!ready) return;
    const tl = gsap.timeline({ delay: INTRO.instrAt });
    tl.to(els, {
      scaleX: 1,
      opacity: (i) => ticks[i]?.alpha ?? 0.3,
      duration: M.introDur,
      stagger: M.introStagger,
      ease: "power3.out",
      overwrite: true,
      onComplete: () => {
        st.current.introDone = true;
      },
    });
    const speed = () => {
      tl.timeScale(Math.max(1, introClock.scale));
    };
    gsap.ticker.add(speed);
    return () => {
      gsap.ticker.remove(speed);
      tl.kill();
    };
  }, [mode, ticks, ready]);

  // Ruler frame: ticks, needle, readout, zoom bracket, ghost.
  useEffect(() => {
    if (!mode || !geom.docH) return;
    const full = mode === "full";
    const tick = (_: number, dtMs: number) => {
      const n = st.current;
      const { docH, vh } = n.geom;
      if (!vh) return;
      const dt = Math.min(dtMs / 1e3, 0.1) || 0.016;
      const sy = window.scrollY;
      const max = Math.max(1, docH - vh);
      const f = clamp01(sy / max);
      const map = rulerMap(vh, L.edgePad);
      const drift = map.drift(f);
      if (tickTrack.current) tickTrack.current.style.transform = `translate3d(0, ${-sy + drift}px, 0)`;
      const ny = map.base + f * map.span;
      if (needle.current) {
        needle.current.style.transform = `translate3d(0, ${ny}px, 0)`;
        needle.current.style.opacity = String(clamp01(f / Math.max(0.001, LOOK.needleFadePct / 100)));
      }
      const above = ny > vh - 26;
      if (readout.current && above !== n.readoutAbove) {
        n.readoutAbove = above;
        readout.current.style.top = above ? "-14px" : "4px";
      }
      const pct = Math.round(100 * f);
      if (pct !== n.prevPct) {
        n.prevPct = pct;
        railRef.current?.setAttribute("aria-valuenow", String(pct));
        const s = String(pct).padStart(3, "0");
        for (let k = 0; k < 3; k++) {
          const d = s.charCodeAt(k) - 48;
          if (d !== n.prevDigits[k]) {
            n.prevDigits[k] = d;
            const col = digitCols.current[k];
            if (col) col.style.transform = `translateY(${-d}em)`;
          }
        }
      }
      if (full) {
        rulerZoom.target = n.zoomIntent || rulerZoom.dragging ? 1 : 0;
        rulerZoom.p += (rulerZoom.target - rulerZoom.p) * (1 - Math.exp(-M.zoomLerp * dt));
        if (rulerZoom.target === 0 && rulerZoom.p < 5e-4) rulerZoom.p = 0;
        if (rulerZoom.target === 1 && rulerZoom.p > 0.9995) rulerZoom.p = 1;
      }
      const z = full ? rulerZoom.p : 0;
      if (bracket.current) {
        const b = bracket.current;
        b.style.transform = `translate3d(0, ${map.base + (sy / docH) * map.span}px, 0)`;
        b.style.height = `${(vh / docH) * map.span}px`;
        b.style.opacity = String(z);
      }
      if (ghostBox.current) {
        const g = ghostBox.current;
        if (n.ghostActive) {
          g.style.transform = `translate3d(0, ${n.ghostY}px, 0)`;
          g.style.opacity = String(LOOK.ghostAlpha * (0.2 + 0.8 * z));
        } else g.style.opacity = "0";
      }
      if (full && n.introDone && ticks.length) {
        const at = f * docH;
        const velK = clamp01(Math.abs(n.vel) / 3e3);
        const moved = z > 0 || n.zoomWrote;
        const spans = railOccupancy.spans;
        for (let i = 0; i < ticks.length; i++) {
          const live = ticks[i].docY - sy + drift;
          const mapped = map.base + (ticks[i].pct / 100) * map.span;
          if (moved) {
            const row = tickRows.current[i];
            if (row) row.style.transform = z > 0 ? `translate3d(0, ${z * (mapped - live)}px, 0)` : "";
          }
          const lab = tickLabels.current[i];
          if (lab) {
            const y = live + z * (mapped - live);
            let keep = 1;
            if (LOOK.yieldPad > 0 && z < 1)
              for (const sp of spans) {
                const d = y < sp.top ? sp.top - y : y > sp.bottom ? y - sp.bottom : 0;
                if (d < LOOK.yieldPad) {
                  const k = 1 - sp.k * (1 - d / LOOK.yieldPad);
                  if (k < keep) keep = k;
                }
              }
            lab.style.opacity = String(LOOK.labelAlpha * (1 - (1 - keep) * (1 - z)));
          }
          const el = tickEls.current[i];
          if (!el) continue;
          const dist = Math.abs(ticks[i].docY - at);
          if (dist < M.velRadius && M.velRadius > 0) {
            const e = 1 - dist / M.velRadius;
            const r = velK * e * e;
            el.style.transform = `scaleX(${1 + M.velMax * r})`;
            el.style.opacity = String(Math.min(1, ticks[i].alpha + 0.6 * r));
          } else {
            el.style.transform = "scaleX(1)";
            el.style.opacity = String(ticks[i].alpha);
          }
        }
        n.zoomWrote = z > 0;
      }
    };
    gsap.ticker.add(tick);
    return () => gsap.ticker.remove(tick);
  }, [mode, geom, ticks]);

  // Headings: queue → riding the rail → flipped into the top stack.
  useEffect(() => {
    if (mode !== "full" || !metrics || !sections.length || !geom.docH) return;
    const side = -1;
    const frame = (_: number, dtMs: number) => {
      const r = st.current;
      const { docH, vh, vw } = geom;
      const dt = Math.min(dtMs / 1e3, 0.1) || 0.016;
      const sy = window.scrollY;
      const max = Math.max(1, docH - vh);
      const f = clamp01(sy / max);
      const map = rulerMap(vh, L.edgePad);
      const drift = map.drift(f);
      const v = (sy - r.lastY) / dt;
      r.lastY = sy;
      r.vel += (v - r.vel) * (1 - Math.exp(-6 * dt));
      const line = (L.thresholdPct / 100) * vh;
      const top = NAV_H + L.topPad;
      const queueY = vh - L.queuePad;
      const D = L.headingPx;
      const ride = L.ridingPx / D;
      const qs = L.queuePx / D;
      const railX = vw - L.railW / 2;
      const zoom = easeInOutCubic(rulerZoom.p);
      const heroLive = heroWordmark.ready && heroWordmark.els.length > 0;
      if (heroLive) heroWordmark.read();
      const heroTop = heroLive ? heroWordmark.docCenterY - 0.5 * heroWordmark.fontPx : 0;

      const S = sections.map((s, i) => {
        const m = metrics[s.label];
        const rideLen = (m?.total ?? 0) * D * ride;
        const vy = s.anchor - sy + drift;
        let flipP = 0;
        let detachP = 0;
        let scrollFlip: { start: number; end: number } | null = null;
        if (i !== 0 || s.isHero) {
          if (s.isHero) {
            detachP = 1;
            const start = Math.max(0, heroTop - NAV_H - M.heroLead);
            const zone = Math.max(1, M.heroZone);
            flipP = clamp01((sy - start) / zone);
            scrollFlip = { start, end: start + zone };
          } else {
            flipP = clamp01((line + M.flipZone - vy) / M.flipZone);
            if (s.anchor - max > line) {
              const start = Math.min(s.bottom - vh, max - 24);
              const span = Math.max(24, max - start);
              flipP = Math.max(flipP, clamp01((sy - start) / span));
              scrollFlip = { start, end: max };
            }
          }
        } else {
          flipP = 1;
          detachP = 1;
        }
        return { v: vy, rideLen, flipP, scrollFlip, detachP, yq: queueY };
      });
      {
        let k = 0;
        for (let i = sections.length - 1; i >= 0; i--) {
          if (sections[i].isHero || i === 0) continue;
          const s = S[i];
          s.yq = queueY - L.queueSlot * k;
          s.detachP = clamp01((s.yq + M.detachZone - (s.v + s.rideLen)) / M.detachZone);
          k += 1 - s.detachP;
        }
      }
      railOccupancy.spans.length = 0;
      let flipped = 0;
      let partial = 0;
      for (const s of S) {
        if (s.flipP >= 1) flipped++;
        else if (s.flipP > 0) partial += s.flipP;
      }
      let topK = 0;
      let bottomK = 0;
      for (let i = 0; i < S.length; i++) {
        if (S[i].flipP > topK) topK = S[i].flipP;
        if (!sections[i].isHero) bottomK = Math.max(bottomK, 1 - S[i].detachP);
      }
      if (topPool.current) topPool.current.style.opacity = String(LOOK.poolAlpha * topK);
      if (bottomPool.current) bottomPool.current.style.opacity = String(LOOK.poolAlpha * bottomK);

      const flat = (m: Metrics, k: number, y: number, scale: number, alpha: number): Pose => {
        const c = (m.cum[k] + m.adv[k] / 2) * D * scale;
        const x = L.railW + L.textPad + (m.total * D * scale - c);
        return { x: vw - x, y, rot: 0, scale, alpha };
      };
      const riding = (m: Metrics, k: number, y: number): Pose => ({
        x: railX,
        y: y + (m.total - m.cum[k] - m.adv[k] / 2) * D * ride,
        rot: -90,
        scale: ride,
        alpha: LOOK.queueAlpha,
      });

      for (let i = 0; i < sections.length; i++) {
        const sec = sections[i];
        const hero = sec.isHero && heroLive;
        const m = metrics[sec.label];
        const h = heads.current[i];
        if (!m || !h || (sec.isHero && !hero) || (sec.isHero && heroWordmark.forming)) continue;
        const { v: vy, rideLen, flipP, detachP, yq } = S[i];
        const N = m.adv.length;
        const rest = (k: number): Pose => ({
          x: heroWordmark.restX[k],
          y: heroWordmark.restY[k],
          rot: 0,
          scale: heroWordmark.fontPx / D,
          alpha: 1,
        });
        let t: number;
        let from: (k: number) => Pose;
        let to: (k: number) => Pose;
        let reverse = false;
        if (flipP > 0) {
          t = flipP;
          reverse = true;
          from = hero ? rest : (k) => riding(m, k, vy);
          if (flipP >= 1) {
            const settle = i === flipped - 1 ? partial : 1;
            const y = top + i * L.queueSlot + L.currentGap * (1 - settle);
            const sc = 1 - (1 - qs) * settle;
            const al = 1 - (1 - LOOK.queueAlpha) * settle;
            to = (k) => flat(m, k, y, sc, al);
          } else to = (k) => flat(m, k, top + i * L.queueSlot + L.currentGap, 1, 1);
        } else if (detachP < 1) {
          t = detachP;
          reverse = true;
          const y = yq - rideLen;
          to = (k) => riding(m, k, y);
          from = (k) => flat(m, k, yq, qs, LOOK.queueAlpha);
        } else {
          t = 1;
          from = to = hero ? rest : (k) => riding(m, k, vy);
        }
        const span = 1 + (N - 1) * M.stagger;
        const mapY = map.base + ((sec.isHero ? 0 : sec.anchor) / docH) * map.span;
        const els = h.letters;
        const unscale = hero ? D / heroWordmark.fontPx : 1;
        // The real hero word shows while it rests; its copies take over in flight.
        const flying = hero && (flipP > 0 || zoom > 0);
        if (hero) {
          for (const o of heroWordmark.els) o.style.visibility = flying ? "hidden" : "";
          const fs = `${heroWordmark.fontPx}px`;
          for (const el of els) if (el && el.style.fontSize !== fs) el.style.fontSize = fs;
        }
        const z = hero ? zoom * Math.min(1, flipP) : zoom;
        const hk = (hoverK[i] += (+(hover.current === i) - hoverK[i]) * (1 - Math.exp(-dt / 0.08)));
        const flash = clamp01((flashAt[i] - performance.now()) / 350);
        let x0 = Infinity;
        let x1 = -Infinity;
        let y0 = Infinity;
        let y1 = -Infinity;
        let shown = 0;
        for (let k = 0; k < N; k++) {
          const el = els[k];
          if (!el) continue;
          const order = reverse ? N - 1 - k : k;
          const e = easeInOutCubic(clamp01(t * span - order * M.stagger));
          const a = from(k);
          const b = to(k);
          const cx = (a.x + b.x) / 2 + side * M.arc;
          const cy = (a.y + b.y) / 2;
          const u = 1 - e;
          let x = u * u * a.x + 2 * u * e * cx + e * e * b.x;
          let y = u * u * a.y + 2 * u * e * cy + e * e * b.y;
          let rot = a.rot + (b.rot - a.rot) * e;
          let sc = a.scale + (b.scale - a.scale) * e;
          let al = a.alpha + (b.alpha - a.alpha) * e;
          if (z > 0) {
            const p = flat(m, k, mapY, qs, LOOK.mapAlpha);
            x += (p.x - x) * z;
            y += (p.y - y) * z;
            rot *= 1 - z;
            sc += (p.scale - sc) * z;
            al += (p.alpha - al) * z;
          }
          el.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%) rotate(${rot}deg) scale(${sc * unscale})`;
          if (hero) {
            const w = flipP > 0 ? e : 0;
            el.style.fontWeight = String(Math.round(WORDMARK_WEIGHT - (WORDMARK_WEIGHT - DISPLAY_WEIGHT) * w));
            el.style.fontStretch = `${(WORDMARK_STRETCH - (WORDMARK_STRETCH - DISPLAY_STRETCH) * w).toFixed(1)}%`;
          }
          el.style.opacity = hero && !flying ? "0" : "1";
          const ink = al + (1 - al) * hk;
          const base = ink >= 0.995 ? "var(--ruler-ink)" : `color-mix(in srgb, var(--ruler-ink) ${(100 * clamp01(ink)).toFixed(1)}%, var(--ruler-bg))`;
          el.style.color = flash > 0.01 ? `color-mix(in srgb, var(--ruler-accent-ink) ${(70 * flash).toFixed(0)}%, ${base})` : base;
          if (al > shown) shown = al;
          const hw = (m.adv[k] * D * sc) / 2 + 2;
          const hh = (D * sc) / 2 + 2;
          const upright = Math.abs(rot) > 45;
          const ex = upright ? hh : hw;
          const ey = upright ? hw : hh;
          if (x - ex < x0) x0 = x - ex;
          if (x + ex > x1) x1 = x + ex;
          if (y - ey < y0) y0 = y - ey;
          if (y + ey > y1) y1 = y + ey;
        }
        const occ = sec.isHero ? 0 : detachP * (1 - flipP);
        if (occ > 0.02) railOccupancy.spans.push({ top: vy, bottom: vy + rideLen, k: occ });
        if (h.hit && isFinite(x0)) {
          h.hit.style.left = `${x0 - 2}px`;
          h.hit.style.top = `${y0 - 2}px`;
          h.hit.style.width = `${x1 - x0 + 4}px`;
          h.hit.style.height = `${y1 - y0 + 4}px`;
          h.hit.style.pointerEvents = shown > 0.05 && (!sec.isHero || flipP > 0.05) ? "auto" : "none";
        }
      }

      // A flip left half-done at rest resolves itself with a short damped scroll.
      const lenis = getLenis();
      const now = performance.now();
      const mid = S.findIndex((s) => s.flipP > 0.04 && s.flipP < 0.96);
      if (rulerZoom.dragging) r.armed = true;
      if (r.snapping) {
        if (mid < 0) r.snapping = false;
      } else if (mid >= 0 && r.armed && !r.jumping && Math.abs(r.vel) < 30 && lenis && !rulerZoom.dragging && rulerZoom.p < 0.3) {
        if (r.snapSince === null) r.snapSince = now;
        else if (now - r.snapSince > M.snapDelay) {
          const s = S[mid];
          const sec = sections[mid];
          let goal: number;
          if (s.scrollFlip) goal = s.flipP >= 0.5 ? s.scrollFlip.end + 4 : s.scrollFlip.start - 4;
          else goal = sec.anchor + drift - (s.flipP >= 0.5 ? line - 4 : line + M.flipZone + 4);
          const bounds = (q: Section, w: (typeof S)[number]) => {
            const yFlip = q.anchor + drift - line - 0.04 * M.flipZone;
            const yUnflip = q.anchor + drift - line - 0.96 * M.flipZone;
            if (!w.scrollFlip) return { yFlip, yUnflip };
            const len = w.scrollFlip.end - w.scrollFlip.start;
            const of = w.scrollFlip.start + 0.96 * len;
            const ou = w.scrollFlip.start + 0.04 * len;
            return q.isHero ? { yFlip: of, yUnflip: ou } : { yFlip: Math.min(yFlip, of), yUnflip: Math.min(yUnflip, ou) };
          };
          let safe = goal;
          for (let i = 0; i < S.length; i++) {
            if (i === mid) continue;
            const b = bounds(sections[i], S[i]);
            if (S[i].flipP >= 0.96) safe = Math.max(safe, b.yFlip + 2);
            else if (S[i].flipP <= 0.04) safe = Math.min(safe, b.yUnflip - 2);
          }
          const own = bounds(sec, s);
          const keep = s.flipP >= 0.5 ? safe >= own.yFlip : safe <= own.yUnflip;
          const y = Math.max(0, Math.min(max, keep ? safe : goal));
          r.snapping = true;
          r.armed = false;
          r.snapSince = null;
          lenis.scrollTo(y, {
            duration: M.snapDur,
            easing: easeInOutCubic,
            onComplete: () => {
              r.snapping = false;
            },
          });
        }
      } else r.snapSince = null;
    };
    const arm = () => {
      st.current.armed = true;
    };
    window.addEventListener("wheel", arm, { passive: true });
    window.addEventListener("touchmove", arm, { passive: true });
    window.addEventListener("keydown", arm);
    gsap.ticker.add(frame);
    return () => {
      window.removeEventListener("wheel", arm);
      window.removeEventListener("touchmove", arm);
      window.removeEventListener("keydown", arm);
      gsap.ticker.remove(frame);
    };
  }, [mode, metrics, sections, geom, hoverK, flashAt]);

  // Hand the hero letters back untouched when the ruler leaves.
  useEffect(
    () => () => {
      for (const e of heroWordmark.els) e.style.visibility = "";
    },
    [mode],
  );

  const zoomSoon = (on: boolean) => {
    const n = st.current;
    window.clearTimeout(n.zoomTimer);
    n.zoomTimer = window.setTimeout(
      () => {
        n.zoomIntent = on;
      },
      on ? M.zoomInDelay : M.zoomOutDelay,
    );
  };
  useEffect(
    () => () => {
      window.clearTimeout(st.current.zoomTimer);
      rulerZoom.target = 0;
      rulerZoom.p = 0;
      rulerZoom.dragging = false;
    },
    [],
  );

  const jumpToRatio = (clientY: number) => {
    const n = st.current;
    const map = rulerMap(n.geom.vh, L.edgePad);
    const y = clamp01((clientY - map.base) / map.span) * Math.max(1, n.geom.docH - n.geom.vh);
    const dist = Math.abs(y - window.scrollY);
    scrollToY(y, M.jumpDur * (0.4 + 0.6 * Math.min(1, dist / (2.5 * n.geom.vh))));
  };

  const endDrag = (e: React.PointerEvent) => {
    if (!rulerZoom.dragging) return;
    rulerZoom.dragging = false;
    const r = railRef.current?.getBoundingClientRect();
    const inside = r && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    if (!inside) {
      st.current.ghostActive = false;
      zoomSoon(false);
    }
  };

  const jumpTo = (i: number, s: Section) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    flashAt[i] = performance.now() + 350;
    st.current.armed = false;
    st.current.jumping = true;
    const el = document.getElementById(s.id);
    const y = s.isHero ? 0 : el ? el.getBoundingClientRect().top + window.scrollY : s.anchor;
    const lenis = getLenis();
    if (lenis)
      lenis.scrollTo(y, {
        duration: M.jumpDur,
        easing: easeOutExpo,
        onComplete: () => {
          st.current.jumping = false;
        },
      });
    else {
      window.scrollTo({ top: y });
      st.current.jumping = false;
    }
  };

  const full = mode === "full";
  const queueW = useMemo(() => {
    let w = 260;
    if (metrics) for (const s of LABELS) w = Math.max(w, (metrics[s.label]?.total ?? 0) * L.headingPx);
    return w + L.railW + L.textPad + LOOK.poolPad;
  }, [metrics]);

  return (
    <>
      {mode === "static" && (
        <nav aria-label="Sections" className="ruler-static" style={{ bottom: L.queuePad, right: L.railW + L.textPad }}>
          <div aria-hidden className="ruler-static-pool" style={{ opacity: LOOK.poolAlpha }} />
          <ul>
            {LABELS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  style={{ fontSize: L.queuePx + 2 }}
                  onClick={(e) => {
                    e.preventDefault();
                    document.getElementById(s.id)?.scrollIntoView();
                  }}
                >
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
      {mode && geom.docH > 0 && (
        <div
          ref={railRef}
          role="scrollbar"
          aria-controls="main"
          aria-orientation="vertical"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={0}
          aria-label="Position dans la page"
          className="ruler"
          style={{ width: L.railW }}
          onClick={(e) => {
            if (st.current.dragMoved > 4) return;
            jumpToRatio(e.clientY);
            if (full && ghostLine.current) gsap.fromTo(ghostLine.current, { opacity: 1 }, { opacity: LOOK.ghostAlpha, duration: 0.45 });
          }}
          onPointerEnter={full ? () => zoomSoon(true) : undefined}
          onPointerLeave={
            full
              ? () => {
                  st.current.ghostActive = false;
                  if (!rulerZoom.dragging) zoomSoon(false);
                }
              : undefined
          }
          onPointerMove={
            full
              ? (e) => {
                  const n = st.current;
                  const map = rulerMap(n.geom.vh, L.edgePad);
                  const y = Math.max(map.base, Math.min(map.base + map.span, e.clientY));
                  const p = clamp01((y - map.base) / map.span);
                  n.ghostActive = true;
                  n.ghostY = y;
                  if (rulerZoom.dragging) {
                    n.dragMoved = Math.max(n.dragMoved, Math.abs(e.clientY - n.dragStartY));
                    getLenis()?.scrollTo(p * Math.max(1, n.geom.docH - n.geom.vh), { lerp: M.dragLerp });
                  }
                }
              : undefined
          }
          onPointerDown={
            full
              ? (e) => {
                  e.preventDefault();
                  const n = st.current;
                  n.dragStartY = e.clientY;
                  n.dragMoved = 0;
                  rulerZoom.dragging = true;
                  e.currentTarget.setPointerCapture(e.pointerId);
                }
              : undefined
          }
          onPointerUp={full ? endDrag : undefined}
          onPointerCancel={full ? endDrag : undefined}
        >
          <div
            aria-hidden
            className="ruler-frost"
            style={{ maskImage: frostMask(LOOK.frostSolid, LOOK.frostGamma), WebkitMaskImage: frostMask(LOOK.frostSolid, LOOK.frostGamma) }}
          />
          <div ref={tickTrack} aria-hidden className="ruler-track" style={{ height: geom.docH }}>
            {ticks.map((t, i) => (
              <div
                key={t.pct}
                ref={(e) => {
                  tickRows.current[i] = e;
                }}
                className="ruler-row"
                style={{ top: t.docY }}
              >
                <span
                  ref={(e) => {
                    tickEls.current[i] = e;
                  }}
                  className="ruler-tick"
                  style={{ width: t.major ? LOOK.majorLen : LOOK.minorLen, opacity: full ? 0 : t.alpha }}
                />
                {t.major && (
                  <span
                    ref={(e) => {
                      tickLabels.current[i] = e;
                    }}
                    className="ruler-label"
                    style={{ right: LOOK.majorLen + 4, opacity: LOOK.labelAlpha }}
                  >
                    {t.pct}
                  </span>
                )}
              </div>
            ))}
          </div>
          {full && (
            <div ref={bracket} aria-hidden className="ruler-bracket">
              <div style={{ opacity: LOOK.bracketAlpha }} />
              <span />
              <span />
            </div>
          )}
          <div ref={needle} aria-hidden className="ruler-needle">
            <span className="ruler-needle-line" />
            <span ref={readout} className="ruler-readout">
              <span className="ruler-digits">
                {[0, 1, 2].map((k) => (
                  <span
                    key={k}
                    ref={(e) => {
                      digitCols.current[k] = e;
                    }}
                    className="ruler-digit-col"
                  >
                    {"0123456789".split("").map((d) => (
                      <span key={d}>{d}</span>
                    ))}
                  </span>
                ))}
              </span>
              <span style={{ marginLeft: 2 }}>%</span>
            </span>
          </div>
        </div>
      )}
      {full && geom.docH > 0 && (
        <div ref={ghostBox} aria-hidden className="ruler-ghost" style={{ width: L.railW }}>
          <div ref={ghostLine} style={{ top: -LOOK.ghostThick / 2, width: L.railW, height: LOOK.ghostThick, opacity: LOOK.ghostAlpha }} />
        </div>
      )}
      {full && metrics && (
        <>
          <div aria-hidden className="ruler-pools">
            <div
              ref={topPool}
              className="ruler-pool"
              style={{
                top: 0,
                width: queueW,
                height: NAV_H + L.topPad + Math.max(0, LABELS.length - 1) * L.queueSlot + L.currentGap + L.headingPx + LOOK.poolPad,
                maskImage: poolMask("0%"),
                WebkitMaskImage: poolMask("0%"),
              }}
            />
            <div
              ref={bottomPool}
              className="ruler-pool"
              style={{
                bottom: 0,
                width: queueW,
                height: L.queuePad + LABELS.length * L.queueSlot + LOOK.poolPad,
                maskImage: poolMask("100%"),
                WebkitMaskImage: poolMask("100%"),
              }}
            />
          </div>
          <nav aria-label="Sections" className="ruler-heads">
            {sections.map((s, i) => {
              const h = (heads.current[i] ??= { letters: [], hit: null });
              return (
                <Fragment key={s.id}>
                  <a
                    href={`#${s.id}`}
                    ref={(e) => {
                      h.hit = e;
                    }}
                    aria-label={`Aller à ${SECTIONS[i]?.label ?? s.label}`}
                    className="ruler-hit"
                    onClick={jumpTo(i, s)}
                    onPointerEnter={() => {
                      hover.current = i;
                    }}
                    onPointerLeave={() => {
                      if (hover.current === i) hover.current = -1;
                    }}
                  />
                  {s.label.split("").map((ch, k) => (
                    <span
                      key={k}
                      ref={(e) => {
                        h.letters[k] = e;
                      }}
                      aria-hidden
                      className={s.isHero ? `${LETTER_CLASS} is-hero` : LETTER_CLASS}
                      style={{ fontSize: L.headingPx }}
                    >
                      {ch}
                    </span>
                  ))}
                </Fragment>
              );
            })}
          </nav>
        </>
      )}
      <RailMobile />
    </>
  );
}

/** Below 1024px: a thin progress bar with the current section's name. */
function RailMobile() {
  const [active, setActive] = useState(0);
  const root = useRef<HTMLElement>(null);
  useGSAP(() => {
    const triggers = SECTIONS.map((s, i) =>
      ScrollTrigger.create({
        trigger: `#${s.id}`,
        start: "top 50%",
        end: "bottom 50%",
        onToggle: (t) => {
          if (t.isActive) setActive(i);
        },
      }),
    );
    const bar = root.current?.querySelector("i");
    const setBar = bar ? gsap.quickTo(bar, "scaleX", { duration: 0.3, ease: "power3.out" }) : null;
    const main = ScrollTrigger.create({
      start: 0,
      end: () => ScrollTrigger.maxScroll(window),
      onUpdate: (t) => setBar?.(t.progress),
    });
    return () => {
      triggers.forEach((t) => t.kill());
      main.kill();
    };
  }, []);
  return (
    <aside ref={root} className="rail-mobile" aria-hidden>
      <span>
        {String(active + 1).padStart(2, "0")} / {String(SECTIONS.length).padStart(2, "0")}
      </span>
      <span>{SECTIONS[active].label}</span>
      <i />
    </aside>
  );
}
