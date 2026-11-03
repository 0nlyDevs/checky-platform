import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { Component, useEffect, useMemo, useRef, type ReactNode, type RefObject } from "react";
import { HERO_CLIPS, REEL_CLIP } from "../content/hero";
import { INTRO, introClock } from "../lib/intro";
import { HERO_PHASE as PH, heroScroll, smoothstep as sstep } from "../lib/heroScroll";
import { createClipSources } from "./clipSources";

/* ---------- Tuning (mirrors the reference galaxy hero) ---------- */

const LAYOUT = {
  arms: 6,
  turns: 1.05,
  rMaxFrac: 0.7,
  birthFrac: 0.08,
  cardN: 64,
  tunedMpx: 1.65,
  cardHFrac: 0.25,
  armJitter: 0.76,
  ticksPerArm: 16,
  circFrac: 0.56,
  dedupPx: 300,
};
const MOBILE = { mpx: 0.6, arms: 3, turns: 0.7, cardN: 14, rMax: 0.8, cardH: 0.3, birth: 0.08, densityX: 1.15 };
const MOTION = {
  idleSpeed: 0.57,
  scrub: 0.2,
  spinDeg: -50,
  wobbleAmp: 6,
  wobbleFreq: 0.25,
  introDur: 4,
  rollChunk: 0.12,
  burstX: 3,
  burstDur: 2.5,
  waveBand: 220,
  waveAber: 0.2,
  waveLag: 0.4,
  perfFloor: 30,
};
const POINTER = {
  fieldPx: 320,
  tiltDeg: 0,
  tugPx: 8,
  mouseWarp: 200,
  flareAdd: 0.032,
  flareDecay: 3,
  holdTau: 0.15,
  restTau: 1,
  holdWobble: 1.2,
  targetTau: 0.25,
  rippleSpeed: 900,
  rippleWidth: 140,
  rippleAmp: 0.016,
  rippleWarp: 22,
  rippleLife: 1.8,
  clickAmp: 20,
  clickDur: 0.75,
  clickWidth: 0.14,
  boostScale: 3,
  boostTau: 0.18,
};
const LOOK = {
  density: 0.82,
  cornerPx: 10,
  innerCap: 0.45,
  aspectEnd: 0.3,
  blurMax: 0.12,
  blurEnd: 0.18,
  fadeBand: 0.15,
  aberration: 0.019,
  curvePx: 32,
  frameAlpha: 0.22,
  lineAlpha: 0.15,
  tickAlpha: 0.3,
  lineW: 2,
  pulseAlpha: 0.72,
  pulseSpeed: 0.19,
  pulseWidth: 0.05,
  pulseW: 3.5,
  pulseCount: 3,
  pulseHue: 0,
};

/** 3D choreography of the scroll: disc tilt, tunnel, torch. */
const STAGE3D = {
  tiltDeg: 62,
  /** How much a wall card turns from the tunnel axis toward the camera (0 = flat on the wall). */
  wallLean: 0.9,
  tunnelRFrac: 0.33,
  tunnelFar: -2800,
  tunnelNear: 700,
  tunnelStagger: 0.12,
  tunnelSpan: 0.26,
  cardGrow: 1.25,
  depthFadeAt: -3300,
  depthFadeLen: 900,
  torchAlpha: 0.32,
  torchSize: 2.2,
  dimTo: 0.35,
  frontWFrac: 0.34,
  radius: 20,
};

/** Dark theme colours of the stage, resolved to opaque sRGB. */
const THEME = {
  bg: "#0a0a0b",
  // rgba(243,242,238,0.4) over the background
  lineStrong: "#666563",
  // ink and paper only: the comets run in paper
  accent: "#f3f2ee",
};

const TORCH_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const TORCH_FRAG = /* glsl */ `
  uniform float uAlpha;
  uniform vec3 uColor;
  varying vec2 vUv;
  void main() {
    vec2 d = (vUv - 0.5) * 2.0;
    float r = dot(d, d);
    float g = exp(-r * 3.2) * (1.0 - smoothstep(0.7, 1.0, r));
    // Premultiplied: adds light without darkening the transparent canvas.
    float k = g * uAlpha;
    gl_FragColor = vec4(uColor * k, k);
  }
`;

/* ---------- Shaders ---------- */

const CARD_VERT = /* glsl */ `
  uniform float uCurve;
  uniform float uWarp;
  uniform vec2 uMouse;
  uniform vec2 uSize;
  out vec2 vUv;
  void main() {
    vUv = uv;
    vec4 world = modelMatrix * vec4(position, 1.0);
    // Bow the plane toward the camera: strongest at the centre, flat at the edges.
    float d2 = dot(position.xy, position.xy);
    world.z += uCurve * (0.25 - d2) * 2.0;
    // The cursor's weight: a local bulge at the point of the card nearest the mouse.
    vec2 dpx = (position.xy - uMouse) * uSize;
    float rr = max(uSize.x, uSize.y) * 0.6;
    world.z += uWarp * exp(-dot(dpx, dpx) / (rr * rr));
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const CARD_FRAG = /* glsl */ `
  uniform sampler2D uMap;
  uniform vec2 uRepeat;
  uniform vec2 uOffset;
  uniform vec3 uBg;
  uniform float uBlur;
  uniform float uTexA;
  uniform float uAlpha;
  uniform float uAber;
  uniform vec2 uSize;
  uniform float uRadius;
  uniform vec3 uFrameCol;
  uniform float uFrameA;
  uniform vec4 uClick[4];
  uniform float uClickW;
  in vec2 vUv;
  out vec4 outColor;

  const vec2 TAPS[12] = vec2[12](
    vec2(-0.326, -0.406), vec2(-0.840, -0.074), vec2(-0.696, 0.457),
    vec2(-0.203, 0.621), vec2(0.962, -0.195), vec2(0.473, -0.480),
    vec2(0.519, 0.767), vec2(0.185, -0.893), vec2(0.507, 0.064),
    vec2(0.896, 0.412), vec2(-0.322, -0.933), vec2(-0.792, -0.598)
  );

  void main() {
    // Click punches: a soft ring pushes the texture outward from the click point.
    vec2 uvL = vUv;
    for (int k = 0; k < 4; k++) {
      if (uClick[k].w > 0.001) {
        vec2 q = (vUv - uClick[k].xy) * uSize;
        float dq = length(q);
        float ring = (dq - uClick[k].z) / max(1.0, uClickW);
        uvL += (q / max(1.0, dq)) * (uClick[k].w * exp(-ring * ring)) / uSize;
      }
    }
    // Cover-fit crop window; samples clamp inside it.
    vec2 uv = uvL * uRepeat + uOffset;
    vec2 lo = uOffset;
    vec2 hi = uOffset + uRepeat;
    vec3 col;
    if (uBlur > 0.0008) {
      float a = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.545) * 6.2832;
      mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
      vec3 acc = texture(uMap, clamp(uv, lo, hi)).rgb;
      for (int i = 0; i < 12; i++) {
        acc += texture(uMap, clamp(uv + rot * TAPS[i] * uBlur, lo, hi)).rgb;
      }
      col = acc / 13.0;
    } else {
      // Chromatic dispersion growing toward the card edges.
      vec2 d = vUv - 0.5;
      vec2 shift = d * dot(d, d) * 4.0 * uAber;
      col = vec3(
        texture(uMap, clamp(uv + shift, lo, hi)).r,
        texture(uMap, clamp(uv, lo, hi)).g,
        texture(uMap, clamp(uv - shift, lo, hi)).b
      );
    }
    col = mix(uBg, col, uTexA);

    // Rounded-rect SDF in card px, with a hairline frame riding the same edge.
    vec2 q = abs((vUv - 0.5) * uSize) - (0.5 * uSize - vec2(uRadius));
    float dEdge = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - uRadius;
    float frameBand = 1.0 - smoothstep(0.5, 1.5, abs(dEdge + 1.0));
    col = mix(col, uFrameCol, frameBand * uFrameA);
    float aa = 1.0 - smoothstep(-0.75, 0.75, dEdge);
    outColor = vec4(col, uAlpha * aa);
  }
`;

const ARM_VERT = /* glsl */ `
  attribute vec2 aN;
  attribute float aSide;
  attribute float aT;
  attribute float aArm;
  uniform float uTime;
  uniform float uSpeed;
  uniform float uWidth;
  uniform float uCount;
  uniform float uBaseW;
  uniform float uPulseW;
  uniform float uWaveR;
  uniform float uWaveBand;
  varying float vG;
  varying float vSide;
  varying float vArm;
  void main() {
    // Comets travel outward, arms dephased by the golden conjugate.
    float d = fract(aT * uCount - uTime * uSpeed + aArm * 0.618);
    float s = d - 0.5;
    float sig = uWidth * (s < 0.0 ? 1.7 : 0.55);
    float g = exp(-0.5 * (s / sig) * (s / sig));
    g *= smoothstep(0.04, 0.14, aT);
    g *= clamp((uWaveR - length(position.xy)) / uWaveBand, 0.0, 1.0);
    vG = g;
    vSide = aSide;
    vArm = aArm;
    float w = uBaseW + uPulseW * g;
    vec3 p = position;
    p.xy += aN * aSide * w * 0.5;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const ARM_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3 uColor;
  uniform float uAlpha;
  uniform vec3 uPulseColor;
  uniform float uPulseAlpha;
  uniform float uHue;
  varying float vG;
  varying float vSide;
  varying float vArm;

  vec3 hueRotate(vec3 color, float a) {
    const mat3 toYIQ = mat3(
      0.299, 0.587, 0.114,
      0.596, -0.274, -0.322,
      0.211, -0.523, 0.312);
    const mat3 toRGB = mat3(
      1.0, 0.956, 0.621,
      1.0, -0.272, -0.647,
      1.0, -1.106, 1.703);
    vec3 yiq = color * toYIQ;
    float h = atan(yiq.z, yiq.y) + a;
    float c = length(yiq.yz);
    return clamp(vec3(yiq.x, c * cos(h), c * sin(h)) * toRGB, 0.0, 1.0);
  }

  void main() {
    float edge = 1.0 - smoothstep(0.45, 1.0, abs(vSide));
    float g = clamp(vG, 0.0, 1.0);
    vec3 pulseCol = hueRotate(uPulseColor, vArm * uHue * 6.28318);
    vec3 col = mix(uColor, pulseCol, g);
    gl_FragColor = vec4(col, (uAlpha + uPulseAlpha * vG) * edge);
  }
`;

/* ---------- Helpers ---------- */

const clamp01 = (e: number) => Math.max(0, Math.min(1, e));
const fract = (e: number) => ((e % 1) + 1) % 1;
const easeOutCubic = (e: number) => 1 - Math.pow(1 - e, 3);
function smooth(e: number, t: number, a: number) {
  const r = clamp01((a - e) / (t - e));
  return r * r * (3 - 2 * r);
}
function hexVec(hex: string) {
  const n = parseInt(hex.replace("#", ""), 16);
  return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}

export interface GalaxyPointer {
  x: number;
  y: number;
  active: boolean;
  clicks: number;
}
export interface Ripple {
  x: number;
  y: number;
  start: number;
}
interface Punch {
  card: number;
  u: number;
  v: number;
  start: number;
}

/* ---------- Scene ---------- */

function Field({ onScreen, pointer, ripples }: { onScreen: boolean; pointer: RefObject<GalaxyPointer>; ripples: RefObject<Ripple[]> }) {
  const size = useThree((s) => s.size);
  const group = useRef<THREE.Group>(null);
  const disc = useRef<THREE.Group>(null);
  const torch = useRef<THREE.Mesh>(null);
  const meshes = useRef<(THREE.Mesh | null)[]>([]);
  const punches = useRef<Punch[]>([]);
  const st = useRef({
    time: 0,
    idleP: 0,
    spin: 0,
    cullTimer: 0,
    frameEma: 1 / 60,
    perfScale: 1,
    lastP: 0,
    holdTarget: 0,
    holdRest: 0,
    fieldK: 1,
    targetI: -1,
    useCounter: 1e4,
    lastClicks: 0,
    boostOn: false,
    boostK: 0,
    boostCard: -1,
    pick: -1,
    pickS: 0,
  });
  const tmp = useMemo(
    () => ({
      v: new THREE.Vector3(),
      vt: new THREE.Vector3(),
      qa: new THREE.Quaternion(),
      qb: new THREE.Quaternion(),
      q: new THREE.Quaternion(),
      e: new THREE.Euler(),
      de: new THREE.Euler(),
      m: new THREE.Matrix4(),
      t: new THREE.Vector3(),
      y: new THREE.Vector3(),
      n: new THREE.Vector3(),
      id: new THREE.Quaternion(),
    }),
    [],
  );

  const sources = useMemo(() => createClipSources(HERO_CLIPS, { colorSpace: THREE.NoColorSpace }), []);
  useEffect(() => () => sources.forEach((s) => s.dispose()), [sources]);
  // The rumour reel: the card the torch picks shows it.
  const reel = useMemo(() => createClipSources([REEL_CLIP], { colorSpace: THREE.NoColorSpace })[0], []);
  useEffect(() => () => reel.dispose(), [reel]);
  const torchMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        transparent: true,
        depthTest: false,
        depthWrite: false,
        blending: THREE.CustomBlending,
        blendSrc: THREE.OneFactor,
        blendDst: THREE.OneMinusSrcAlphaFactor,
        blendSrcAlpha: THREE.OneFactor,
        blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
        uniforms: { uAlpha: { value: 0 }, uColor: { value: new THREE.Color("#f3f2ee") } },
        vertexShader: TORCH_VERT,
        fragmentShader: TORCH_FRAG,
      }),
    [],
  );
  useEffect(() => () => torchMat.dispose(), [torchMat]);
  useEffect(() => {
    const all = [...sources, reel];
    if (onScreen) {
      all.forEach((s) => s.play());
      return;
    }
    const t = setTimeout(() => all.forEach((s) => s.pause()), 2500);
    return () => clearTimeout(t);
  }, [onScreen, sources, reel]);

  const D = useMemo(() => {
    const mpx = (size.width * size.height) / 1e6;
    const mobile = MOBILE.mpx > 0 && mpx < MOBILE.mpx;
    const arms = Math.max(1, Math.round(mobile ? MOBILE.arms : LAYOUT.arms));
    const cardN = mobile
      ? Math.max(4, Math.round(MOBILE.cardN))
      : Math.max(6, Math.min(Math.round(LAYOUT.cardN), Math.round((LAYOUT.cardN * mpx) / LAYOUT.tunedMpx)));
    const halfDiag = Math.hypot(size.width, size.height) / 2;
    const rMax = (mobile ? MOBILE.rMax : LAYOUT.rMaxFrac) * halfDiag;
    const thetaMax = (mobile ? MOBILE.turns : LAYOUT.turns) * Math.PI * 2;
    const b = rMax / thetaMax;
    const cardHCap = Math.min(340, Math.max(70, size.height * (mobile ? MOBILE.cardH : LAYOUT.cardHFrac)));
    const slotsPerArm = Math.max(1, Math.ceil(cardN / arms));
    const thetaBirth = (mobile ? MOBILE.birth : LAYOUT.birthFrac) * thetaMax;
    const thetaExit = (halfDiag + 1.5 * cardHCap) / b;

    const armGeoms: THREE.BufferGeometry[] = [];
    for (let e = 0; e < arms; e++) {
      const off = (e * Math.PI * 2) / arms;
      const pos: number[] = [];
      const nrm: number[] = [];
      const side: number[] = [];
      const at: number[] = [];
      const arm: number[] = [];
      const idx: number[] = [];
      for (let o = 0; o <= 200; o++) {
        const th = 0.3 * thetaBirth + (o / 200) * (thetaExit - 0.3 * thetaBirth);
        const r = b * th;
        const ang = th + off;
        const px = r * Math.cos(ang);
        const py = r * Math.sin(ang);
        const tx = b * Math.cos(ang) - r * Math.sin(ang);
        const ty = b * Math.sin(ang) + r * Math.cos(ang);
        const tl = Math.hypot(tx, ty) || 1;
        for (const s of [-1, 1]) {
          pos.push(px, py, -2);
          nrm.push(-ty / tl, tx / tl);
          side.push(s);
          at.push(o / 200);
          arm.push(e);
        }
        if (o < 200) {
          const k = 2 * o;
          idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2);
        }
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute("aN", new THREE.Float32BufferAttribute(nrm, 2));
      g.setAttribute("aSide", new THREE.Float32BufferAttribute(side, 1));
      g.setAttribute("aT", new THREE.Float32BufferAttribute(at, 1));
      g.setAttribute("aArm", new THREE.Float32BufferAttribute(arm, 1));
      g.setIndex(idx);
      armGeoms.push(g);
    }

    const ticks: number[] = [];
    const perArm = Math.round(LAYOUT.ticksPerArm);
    for (let e = 0; e < arms; e++) {
      const off = (e * Math.PI * 2) / arms;
      for (let k = 0; k < perArm; k++) {
        const th = thetaMax * (0.45 + (0.55 * (k + 0.5)) / perArm);
        const r = b * th;
        const c = Math.cos(th + off);
        const s = Math.sin(th + off);
        ticks.push((r - 6) * c, (r - 6) * s, -2, (r + 6) * c, (r + 6) * s, -2);
      }
    }
    const tickGeom = new THREE.BufferGeometry();
    tickGeom.setAttribute("position", new THREE.Float32BufferAttribute(ticks, 3));

    const circ: number[] = [];
    const R = LAYOUT.circFrac * rMax;
    const dashes = Math.max(8, Math.round((Math.PI * R) / 14));
    for (let k = 0; k < dashes; k++) {
      const a0 = (k / dashes) * Math.PI * 2;
      const a1 = a0 + Math.PI / dashes;
      circ.push(R * Math.cos(a0), R * Math.sin(a0), -2, R * Math.cos(a1), R * Math.sin(a1), -2);
    }
    const circGeom = new THREE.BufferGeometry();
    circGeom.setAttribute("position", new THREE.Float32BufferAttribute(circ, 3));

    return { arms, cardN, rMax, thetaMax, thetaBirth, thetaExit, b, cardHCap, slotsPerArm, mobile, armGeoms, tickGeom, circGeom };
  }, [size.width, size.height]);

  useEffect(
    () => () => {
      D.armGeoms.forEach((g) => g.dispose());
      D.tickGeom.dispose();
      D.circGeom.dispose();
    },
    [D],
  );

  const cards = useMemo(
    () =>
      Array.from({ length: D.cardN }, (_, t) => ({
        clip: t % sources.length,
        arm: t % D.arms,
        slot: Math.floor(t / D.arms),
      })),
    [D, sources.length],
  );
  // Paint/priority order: a golden-ratio shuffle, so shed cards are spread evenly.
  const order = useMemo(() => {
    const e = cards.map((_, t) => t);
    e.sort((a, b) => ((0.618034 * a) % 1) - ((0.618034 * b) % 1));
    return e;
  }, [cards]);
  const rank = useMemo(() => {
    const e = new Int32Array(cards.length);
    order.forEach((t, a) => {
      e[t] = a;
    });
    return e;
  }, [cards, order]);

  const materials = useMemo(
    () =>
      cards.map(
        (c) =>
          new THREE.ShaderMaterial({
            glslVersion: THREE.GLSL3,
            vertexShader: CARD_VERT,
            fragmentShader: CARD_FRAG,
            transparent: true,
            depthTest: false,
            depthWrite: false,
            uniforms: {
              uMap: { value: sources[c.clip].texture },
              uRepeat: { value: new THREE.Vector2(1, 1) },
              uOffset: { value: new THREE.Vector2(0, 0) },
              uBg: { value: hexVec(THEME.bg) },
              uBlur: { value: 0 },
              uTexA: { value: 0 },
              uAlpha: { value: 0 },
              uAber: { value: 0 },
              uCurve: { value: 0 },
              uSize: { value: new THREE.Vector2(160, 90) },
              uMouse: { value: new THREE.Vector2(0, 0) },
              uWarp: { value: 0 },
              uClick: { value: [new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4()] },
              uClickW: { value: 20 },
              uRadius: { value: 0 },
              uFrameCol: { value: hexVec(THEME.lineStrong) },
              uFrameA: { value: 0 },
            },
          }),
      ),
    [cards, sources],
  );
  useEffect(() => () => materials.forEach((m) => m.dispose()), [materials]);

  const lineMats = useMemo(() => {
    const circle = new THREE.LineBasicMaterial({ transparent: true, depthTest: false, depthWrite: false, color: THEME.lineStrong });
    const ticks = new THREE.LineBasicMaterial({ transparent: true, depthTest: false, depthWrite: false, color: THEME.lineStrong });
    const arms = new THREE.ShaderMaterial({
      transparent: true,
      depthTest: false,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new THREE.Color(THEME.lineStrong) },
        uAlpha: { value: 0 },
        uPulseColor: { value: new THREE.Color(THEME.accent) },
        uPulseAlpha: { value: 0 },
        uSpeed: { value: 0.22 },
        uWidth: { value: 0.035 },
        uCount: { value: 2 },
        uHue: { value: LOOK.pulseHue },
        uBaseW: { value: 1.2 },
        uPulseW: { value: 3.5 },
        uWaveR: { value: 1e6 },
        uWaveBand: { value: 220 },
      },
      vertexShader: ARM_VERT,
      fragmentShader: ARM_FRAG,
    });
    return { circle, ticks, arms };
  }, []);
  useEffect(
    () => () => {
      lineMats.circle.dispose();
      lineMats.ticks.dispose();
      lineMats.arms.dispose();
    },
    [lineMats],
  );

  const planeGeo = useMemo(() => new THREE.PlaneGeometry(1, 1, 12, 12), []);
  useEffect(() => () => planeGeo.dispose(), [planeGeo]);

  const underlay = useMemo(
    () => [
      ...D.armGeoms.map((g) => new THREE.Mesh(g, lineMats.arms)),
      new THREE.LineSegments(D.circGeom, lineMats.circle),
      new THREE.LineSegments(D.tickGeom, lineMats.ticks),
    ],
    [D, lineMats],
  );

  const buf = useMemo(() => {
    const n = cards.length;
    const nan = new Float32Array(n);
    nan.fill(NaN);
    return {
      K: new Float32Array(2 * n), // positions (pre-spin)
      P: new Float32Array(n), // journey 0..1
      U: new Float32Array(n), // card height
      F: new Float32Array(n), // sweep flare
      X: new Float32Array(n), // target ease (behaviour)
      J: new Float32Array(n), // target ease (optics)
      Y: new Float32Array(n), // hold offset
      Q: new Float32Array(n), // tilt x
      Z: new Float32Array(n), // tilt y
      last: nan,
      texA: new Float32Array(n),
    };
  }, [cards]);
  const lastUse = useMemo(() => {
    const e = new Float32Array(sources.length);
    for (let t = 0; t < e.length; t++) e[t] = t;
    return e;
  }, [sources.length]);

  useFrame((_, delta) => {
    const a = Math.min(delta, 0.05);
    const r = st.current;
    r.time += a;
    const f = r.time;
    const clockT = introClock.t;
    const b = clamp01((clockT - INTRO.cardsAt) / Math.max(0.1, MOTION.introDur));
    const v = easeOutCubic(b);
    const x = clamp01((clockT - INTRO.cardsAt - MOTION.waveLag) / Math.max(0.1, MOTION.introDur));
    const w = easeOutCubic(x);
    const S = clamp01((clockT - INTRO.cardsAt) / Math.max(0.1, MOTION.burstDur));
    const burst = 1 + (MOTION.burstX - 1) * (1 - easeOutCubic(S));
    r.idleP += (a * MOTION.idleSpeed * burst) / 60;
    r.spin += ((a * THREE.MathUtils.degToRad(MOTION.spinDeg)) / 60) * (1 - r.holdRest);
    const R = r.idleP + (window.scrollY * MOTION.scrub) / 1e3;
    const hp = heroScroll.p;
    const discTilt = -THREE.MathUtils.degToRad(STAGE3D.tiltDeg) * sstep(0.03, PH.tiltEnd, hp);
    tmp.de.set(discTilt, 0, r.spin, "XYZ");
    if (disc.current) disc.current.rotation.copy(tmp.de);
    const vw = size.width;
    const vh = size.height;
    const tunnelR = STAGE3D.tunnelRFrac * Math.hypot(vw, vh);
    const torchK = sstep(PH.torchAt, PH.pickAt, hp);
    const dark = sstep(PH.pickAt, PH.darkEnd, hp);
    const pickW = sstep(PH.pickAt, PH.pickEnd, hp);
    if (hp < PH.torchAt - 0.03) r.pick = -1;
    const G = R - r.lastP;
    r.lastP = R;
    const held = r.targetI >= 0;
    r.holdTarget += (+held - r.holdTarget) * (1 - Math.exp(-a / Math.max(0.01, POINTER.holdTau)));
    r.holdRest += (+held - r.holdRest) * (1 - Math.exp(-a / Math.max(0.01, POINTER.restTau)));
    r.fieldK += (+!held - r.fieldK) * (1 - Math.exp(-a / 0.12));

    r.frameEma += (Math.min(delta, 0.25) - r.frameEma) * 0.05;
    // Slow frames shed a few cards, but never during the scroll choreography (a passing load that
    // left holes in the galaxy once back at the top), never below 70 %, and they come back fast.
    if (MOTION.perfFloor > 0 && f > 4) {
      const e = 1 / MOTION.perfFloor;
      if (r.frameEma > e && heroScroll.p < 0.02) r.perfScale = Math.max(0.7, r.perfScale - 0.15 * a);
      else if (r.frameEma < e) r.perfScale = Math.min(1, r.perfScale + 0.6 * a);
    }
    const live = Math.max(6, Math.round(cards.length * r.perfScale));
    const ec = Math.cos(r.spin);
    const ed = Math.sin(r.spin);
    const ptr = pointer.current ?? { x: 0, y: 0, active: false, clicks: 0 };
    // The cursor only plays with the flat galaxy, before the scroll takes over.
    const eh = hp > 0.03 ? { ...ptr, active: false } : ptr;
    const roll = -MOTION.rollChunk * (1 - v);
    const { K, P, U, F: flare, X, J, Y, Q, Z, last, texA } = buf;

    for (let e = 0; e < live; e++) {
      const t = order[e];
      const c = cards[t];
      Y[t] -= G * (t === r.targetI ? Math.max(r.holdTarget, r.holdRest) : r.holdRest);
      let i = Math.max(0, fract((c.slot + 0.5 + c.arm * LAYOUT.armJitter) / D.slotsPerArm + R + Y[t]) + roll);
      if (t === r.pick) i = r.pickS;
      P[t] = i;
      if (t !== r.pick && b >= 1 && !Number.isNaN(last[t]) && Math.abs(i - last[t]) > 0.5) {
        // wrapped back to the centre: take the least recently used clip
        let best = 0;
        for (let k = 1; k < lastUse.length; k++) if (lastUse[k] < lastUse[best]) best = k;
        c.clip = best;
        lastUse[best] = ++r.useCounter;
      }
      last[t] = i;
      const th = D.thetaBirth + i * (D.thetaExit - D.thetaBirth);
      const rad = D.b * th;
      const ang = th + (c.arm * Math.PI * 2) / D.arms;
      const cs = Math.cos(ang);
      const sn = Math.sin(ang);
      const h = MOTION.wobbleAmp * (1 + (POINTER.holdWobble - 1) * r.holdRest) * (1 - X[t]);
      const m = Math.sin(f * MOTION.wobbleFreq * Math.PI * 2 + 2.399 * t);
      const p = Math.cos(f * MOTION.wobbleFreq * Math.PI * 1.4 + 1.713 * t);
      K[2 * t] = rad * cs + h * (-(m * sn) + 0.6 * p * cs);
      K[2 * t + 1] = rad * sn + h * (m * cs + 0.6 * p * sn);
      if (eh.active && POINTER.tugPx > 0 && r.fieldK > 0.001) {
        const sx = ec * K[2 * t] - ed * K[2 * t + 1];
        const sy = ed * K[2 * t] + ec * K[2 * t + 1];
        const dx = eh.x - sx;
        const dy = eh.y - sy;
        const d2 = dx * dx + dy * dy;
        const k = (POINTER.tugPx * Math.exp(-d2 / (POINTER.fieldPx * POINTER.fieldPx)) * r.fieldK * (1 - X[t])) / Math.max(1, Math.sqrt(d2));
        K[2 * t] += (ec * dx + ed * dy) * k;
        K[2 * t + 1] += (-ed * dx + ec * dy) * k;
      }
    }

    // Which card is under the cursor (it brakes and holds).
    let target = -1;
    let best = -1;
    const boost = 1 + (POINTER.boostScale - 1) * r.boostK;
    if (eh.active) {
      const e = r.targetI;
      const pad = POINTER.tugPx + 8;
      let inside = false;
      let insideBoost = false;
      if (e >= 0 && rank[e] < live && U[e] >= 8) {
        const sx = ec * K[2 * e] - ed * K[2 * e + 1];
        const sy = ed * K[2 * e] + ec * K[2 * e + 1];
        const n = Math.abs(eh.x - sx);
        const s = Math.abs(eh.y - sy);
        const u = U[e];
        inside = n <= (8 * u) / 9 + pad && s <= u / 2 + pad;
        const cb = u * (e === r.boostCard ? boost : 1);
        insideBoost = n <= (8 * cb) / 9 + pad && s <= cb / 2 + pad;
      }
      if (inside) target = e;
      else {
        for (let k = 0; k < live; k++) {
          const a2 = order[k];
          if (a2 === e) continue;
          const jr = P[a2];
          if (jr < 0.04 || jr <= best) continue;
          const l = U[a2];
          if (l < 8) continue;
          const sx = ec * K[2 * a2] - ed * K[2 * a2 + 1];
          const sy = ed * K[2 * a2] + ec * K[2 * a2 + 1];
          if (Math.abs(eh.x - sx) <= (8 * l) / 9 && Math.abs(eh.y - sy) <= l / 2) {
            best = jr;
            target = a2;
          }
        }
        if (target < 0 && insideBoost) target = e;
      }
    }
    r.targetI = target;
    if (eh.clicks !== r.lastClicks) {
      r.lastClicks = eh.clicks;
      if (r.targetI >= 0) {
        const e = r.targetI;
        const sx = ec * K[2 * e] - ed * K[2 * e + 1];
        const sy = ed * K[2 * e] + ec * K[2 * e + 1];
        const l = Math.max(1, U[e] * (e === r.boostCard ? boost : 1));
        const asp = 1 + (16 / 9 - 1) * smooth(0, LOOK.aspectEnd, P[e]);
        punches.current.push({ card: e, u: 0.5 + (eh.x - sx) / (l * asp), v: 0.5 + (eh.y - sy) / l, start: f });
        if (punches.current.length > 8) punches.current.shift();
        if (r.boostCard === r.targetI) r.boostOn = !r.boostOn;
        else {
          r.boostCard = r.targetI;
          r.boostOn = true;
        }
      }
    }
    if (r.boostOn && r.targetI !== r.boostCard) r.boostOn = false;
    r.boostK += (+r.boostOn - r.boostK) * (1 - Math.exp(-a / Math.max(0.01, POINTER.boostTau)));
    if (!r.boostOn && r.boostK < 0.001) r.boostCard = -1;

    const rip = ripples.current ?? [];
    for (let e = rip.length - 1; e >= 0; e--) {
      if (rip[e].start < 0) rip[e].start = f;
      if (f - rip[e].start > POINTER.rippleLife) rip.splice(e, 1);
    }
    const pun = punches.current;
    for (let e = pun.length - 1; e >= 0; e--) if (f - pun[e].start > POINTER.clickDur) pun.splice(e, 1);

    const tilt = (POINTER.tiltDeg * Math.PI) / 180;
    for (let e = 0; e < cards.length; e++) {
      const mesh = meshes.current[e];
      if (!mesh) continue;
      if (rank[e] >= live && e !== r.pick) {
        mesh.visible = false;
        continue;
      }
      if (!mesh.visible) {
        U[e] = 0;
        mesh.visible = true;
      }
      const c = cards[e];
      const s = P[e];
      const u = K[2 * e];
      const cy = K[2 * e + 1];
      const d = (X[e] += (+(e === r.targetI) - X[e]) * (1 - Math.exp(-a / Math.max(0.01, POINTER.targetTau))));
      const h = (J[e] += (+(e === r.targetI) - J[e]) * (1 - Math.exp(-a / 0.12)));
      let gap = Infinity;
      let pin = Infinity;
      for (let k = 0; k < live; k++) {
        const a2 = order[k];
        if (a2 === e) continue;
        const l = Math.max((9 * Math.abs(K[2 * a2] - u)) / 16, Math.abs(K[2 * a2 + 1] - cy));
        if (a2 === r.targetI && X[a2] > 0.3) {
          const q = 0.98 * Math.max(0, 2 * l - U[a2]);
          if (q < pin) pin = q;
        } else if (l < gap) gap = l;
      }
      const g = Math.min(D.cardHCap * (LOOK.innerCap + (1 - LOOK.innerCap) * s), LOOK.density * (D.mobile ? MOBILE.densityX : 1) * gap, pin);
      if (d > 0.3) U[e] += (g - U[e]) * (1 - Math.exp(-6 * a));
      else U[e] = g < U[e] ? g : U[e] + (g - U[e]) * (1 - Math.exp(-3 * a));
      const hgt = Math.max(0.001, U[e]) * (e === r.boostCard ? boost : 1);
      const asp0 = 1 + (16 / 9 - 1) * smooth(0, LOOK.aspectEnd, s);
      const asp = e === r.pick ? asp0 + (16 / 9 - asp0) * pickW : asp0;
      const wid = hgt * asp;
      const sx = ec * u - ed * cy;
      const sy = ed * u + ec * cy;
      let field = 0;
      let tx = 0;
      let ty = 0;
      if (eh.active && r.fieldK > 0.001) {
        const dx = eh.x - sx;
        const dy = eh.y - sy;
        const d2 = dx * dx + dy * dy;
        field = Math.exp(-d2 / (POINTER.fieldPx * POINTER.fieldPx)) * r.fieldK;
        const il = 1 / Math.max(1, Math.sqrt(d2));
        ty = tilt * dx * il * field;
        tx = tilt * dy * il * field;
      }
      const ease = 1 - Math.exp(-10 * a);
      Q[e] += (tx * (1 - h) - Q[e]) * ease;
      Z[e] += (ty * (1 - h) - Z[e]) * ease;
      flare[e] = Math.max(flare[e] * Math.exp(-POINTER.flareDecay * a), POINTER.flareAdd * field);
      let N = 0;
      for (let k = 0; k < rip.length; k++) {
        const age = f - rip[k].start;
        const q = (Math.hypot(sx - rip[k].x, sy - rip[k].y) - age * POINTER.rippleSpeed) / POINTER.rippleWidth;
        N += POINTER.rippleAmp * Math.exp(-q * q) * (1 - age / POINTER.rippleLife);
      }
      // Disc pose: on the (tilting, spinning) galaxy plane, card kept upright.
      tmp.v.set(u, cy, 0).applyEuler(tmp.de);
      tmp.qa.setFromEuler(tmp.de).multiply(tmp.q.setFromEuler(tmp.e.set(Q[e], Z[e], -r.spin)));
      // Tunnel pose: on the inside wall of a cylinder along the view axis,
      // deep for young cards, near for old ones, facing the axis.
      const th = Math.atan2(sy, sx);
      const ct = Math.cos(th);
      const stn = Math.sin(th);
      const zt = STAGE3D.tunnelFar + (STAGE3D.tunnelNear - STAGE3D.tunnelFar) * s;
      tmp.vt.set(tunnelR * ct, tunnelR * stn, zt);
      tmp.t.set(-stn, ct, 0);
      tmp.n.set(-ct * STAGE3D.wallLean, -stn * STAGE3D.wallLean, 1).normalize();
      tmp.y.crossVectors(tmp.n, tmp.t);
      tmp.m.makeBasis(tmp.t, tmp.y, tmp.n);
      tmp.qb.setFromRotationMatrix(tmp.m);
      const delay = PH.tunnelAt + STAGE3D.tunnelStagger * (1 - s);
      const morph = sstep(delay, delay + STAGE3D.tunnelSpan, hp);
      tmp.v.lerp(tmp.vt, morph);
      tmp.qa.slerp(tmp.qb, morph);
      let sw = wid * (1 + (STAGE3D.cardGrow - 1) * morph);
      let sh = hgt * (1 + (STAGE3D.cardGrow - 1) * morph);
      let ord = 10 + Math.round(Math.max(0, Math.min(3000, (tmp.v.z + 4000) / 4))) + Math.round(500 * d);

      // The torch picks one card: it turns to face us and lands on the reel
      // slot's column, then follows the slot itself into the next section.
      const picked = e === r.pick;
      let pw = 0;
      if (picked) {
        pw = pickW;
        const slot = heroScroll.slot;
        const fw = slot ? slot.width : Math.min(vw * STAGE3D.frontWFrac, 560);
        const fh = slot ? slot.height : (fw * 9) / 16;
        const fx = slot ? slot.left + slot.width / 2 - vw / 2 : 0;
        const dy = slot ? -(slot.top + slot.height / 2 - vh / 2) : 0;
        const fy = dy;
        tmp.v.lerp(tmp.vt.set(fx, fy, 0), pw);
        tmp.qa.slerp(tmp.id, pw);
        sw += (fw - sw) * pw;
        sh += (fh - sh) * pw;
        ord = 9000;
        if (torch.current) {
          torch.current.position.set(tmp.v.x, tmp.v.y, tmp.v.z - 1);
          torch.current.scale.set(sw * STAGE3D.torchSize, sw * STAGE3D.torchSize, 1);
        }
      }
      mesh.position.copy(tmp.v);
      mesh.quaternion.copy(tmp.qa);
      mesh.scale.set(sw, sh, 1);
      mesh.renderOrder = ord;

      const fadeIn = clamp01(s / LOOK.fadeBand);
      let wave = 1;
      let flash = 0;
      if (b < 1 || (x > 0 && x < 1)) {
        const rr = D.b * (D.thetaBirth + s * (D.thetaExit - D.thetaBirth));
        const band = Math.max(1, MOTION.waveBand);
        if (b < 1) wave = clamp01((v * D.b * D.thetaExit - rr) / band);
        if (x > 0 && x < 1) {
          const q = (rr - w * D.b * D.thetaExit) / band;
          flash = Math.exp(-q * q);
        }
      }
      const src = picked ? reel : sources[c.clip];
      texA[e] += (+src.ready - texA[e]) * (1 - Math.exp(-3 * a));
      const ta = texA[e];
      const un = materials[e].uniforms;
      if (un.uMap.value !== src.texture) un.uMap.value = src.texture;
      const ca = src.aspect;
      if (ca > asp) {
        un.uRepeat.value.set(asp / ca, 1);
        un.uOffset.value.set((1 - asp / ca) / 2, 0);
      } else {
        un.uRepeat.value.set(1, ca / asp);
        un.uOffset.value.set(0, (1 - ca / asp) / 2);
      }
      const flatK = (1 - morph) * (1 - pw);
      const blur0 = Math.max(LOOK.blurMax * (1 - smooth(0, LOOK.blurEnd, s)) * (1 - h), (1 - ta) * LOOK.blurMax, (1 - wave) * LOOK.blurMax);
      un.uBlur.value = picked ? blur0 * (1 - pw) : Math.max(blur0, LOOK.blurMax * 0.6 * torchK);
      un.uTexA.value = ta;
      un.uAber.value = (LOOK.aberration + flare[e] + N + MOTION.waveAber * flash) * (1 - h) * flatK;
      const warpK = Math.min(2, N / Math.max(0.002, POINTER.rippleAmp));
      un.uCurve.value = (LOOK.curvePx + POINTER.rippleWarp * warpK) * (1 - h) * flatK;
      un.uMouse.value.set((eh.x - sx) / Math.max(1, wid), (eh.y - sy) / Math.max(1, hgt));
      un.uWarp.value = POINTER.mouseWarp * field * (1 - h) * flatK;
      un.uSize.value.set(mesh.scale.x, mesh.scale.y);
      const slots = un.uClick.value as THREE.Vector4[];
      let used = 0;
      for (let k = 0; k < pun.length && used < 4; k++) {
        const pk = pun[k];
        if (pk.card !== e) continue;
        const age = (f - pk.start) / Math.max(0.05, POINTER.clickDur);
        if (age < 1) slots[used++].set(pk.u, pk.v, 0.85 * age * Math.max(wid, hgt), POINTER.clickAmp * (1 - age));
      }
      for (; used < 4; used++) slots[used].w = 0;
      un.uClickW.value = POINTER.clickWidth * Math.max(wid, hgt);
      un.uRadius.value = Math.min(LOOK.cornerPx + (STAGE3D.radius - LOOK.cornerPx) * pw, 0.49 * mesh.scale.y);
      un.uFrameA.value = LOOK.frameAlpha;
      const deep = Math.max(0, Math.min(1, (mesh.position.z - STAGE3D.depthFadeAt) / STAGE3D.depthFadeLen));
      const near = Math.max(0, Math.min(1, (900 - mesh.position.z) / 300));
      const depthK = 1 - morph + morph * deep * near;
      const base = fadeIn * wave * depthK;
      un.uAlpha.value = picked ? base + (1 - base) * pw : base * (1 - (1 - STAGE3D.dimTo) * torchK) * (1 - dark);
    }

    const lines = smooth(0, 1, clamp01((clockT - INTRO.instrAt) / 1.2)) * (1 - sstep(PH.tunnelAt, PH.tunnelAt + 0.18, hp));
    lineMats.circle.opacity = LOOK.lineAlpha * lines;
    lineMats.ticks.opacity = LOOK.tickAlpha * lines;
    const au = lineMats.arms.uniforms;
    au.uTime.value = r.time;
    au.uAlpha.value = LOOK.lineAlpha * lines;
    au.uPulseAlpha.value = LOOK.pulseAlpha * lines;
    au.uSpeed.value = LOOK.pulseSpeed;
    au.uWidth.value = LOOK.pulseWidth;
    au.uCount.value = Math.round(LOOK.pulseCount);
    au.uBaseW.value = LOOK.lineW;
    au.uPulseW.value = LOOK.pulseW;
    au.uWaveR.value = v * D.b * D.thetaExit;
    au.uWaveBand.value = Math.max(1, MOTION.waveBand);

    // Pick the torch's card once: a visible one, mid-depth in the tunnel.
    if (r.pick < 0 && hp >= PH.torchAt) {
      let best = -1;
      let score = -Infinity;
      for (let k = 0; k < live; k++) {
        const t = order[k];
        const m = meshes.current[t];
        if (!m || !m.visible) continue;
        const al = materials[t].uniforms.uAlpha.value as number;
        const sc = al - Math.abs(m.position.z + 900) / 1200;
        if (al > 0.25 && sc > score) {
          score = sc;
          best = t;
        }
      }
      // Landing straight past the pin (a jump, a reload): every card is already dark.
      if (best < 0 && live > 0) best = order[0];
      if (best >= 0) {
        r.pick = best;
        r.pickS = P[best];
      }
    }
    torchMat.uniforms.uAlpha.value = STAGE3D.torchAlpha * torchK * (1 - sstep(PH.pickEnd, PH.darkEnd + 0.06, hp)) * (r.pick >= 0 ? 1 : 0);
    if (torch.current) torch.current.visible = torchMat.uniforms.uAlpha.value > 0.002;

    r.cullTimer -= a;
    if (r.cullTimer <= 0) {
      r.cullTimer = 0.25;
      // Two visible cards showing the same clip close together: move the
      // younger one to the clip that is furthest away on screen.
      if (LAYOUT.dedupPx > 0 && b >= 1) {
        const lim = LAYOUT.dedupPx * LAYOUT.dedupPx;
        for (let e = 0; e < live; e++) {
          const a1 = order[e];
          if (materials[a1].uniforms.uAlpha.value < 0.3) continue;
          for (let l = e + 1; l < live; l++) {
            const b1 = order[l];
            if (cards[a1].clip !== cards[b1].clip || materials[b1].uniforms.uAlpha.value < 0.3) continue;
            const dx = K[2 * a1] - K[2 * b1];
            const dy = K[2 * a1 + 1] - K[2 * b1 + 1];
            if (dx * dx + dy * dy > lim) continue;
            const n = P[a1] < P[b1] ? a1 : b1;
            if (n === r.pick) continue;
            const nx = K[2 * n];
            const ny = K[2 * n + 1];
            let pick = -1;
            let score = -Infinity;
            for (let k = 0; k < lastUse.length; k++) {
              if (k === cards[n].clip) continue;
              let near = Infinity;
              for (let q = 0; q < live; q++) {
                const o = order[q];
                if (o === n || cards[o].clip !== k || materials[o].uniforms.uAlpha.value < 0.15) continue;
                const ox = K[2 * o] - nx;
                const oy = K[2 * o + 1] - ny;
                const d2 = ox * ox + oy * oy;
                if (d2 < near) near = d2;
              }
              const sc = Math.min(near, 4 * lim) - 1e-4 * lastUse[k];
              if (sc > score) {
                score = sc;
                pick = k;
              }
            }
            if (pick >= 0) {
              cards[n].clip = pick;
              lastUse[pick] = ++r.useCounter;
            }
          }
        }
      }
    }
  });

  return (
    <group ref={group}>
      <group ref={disc}>
        {underlay.map((o, i) => (
          <primitive key={i} object={o} />
        ))}
      </group>
      <mesh ref={torch} geometry={planeGeo} material={torchMat} renderOrder={8999} visible={false} />
      {cards.map((_, i) => (
        <mesh
          key={i}
          ref={(m) => {
            meshes.current[i] = m;
          }}
          geometry={planeGeo}
          material={materials[i]}
        />
      ))}
    </group>
  );
}

/** Camera in CSS pixels: 30° fov, placed so z=0 maps 1 unit to 1 px. */
function PixelCamera() {
  const get = useThree((s) => s.get);
  const size = useThree((s) => s.size);
  useEffect(() => {
    const camera = get().camera as THREE.PerspectiveCamera;
    const z = size.height / 2 / Math.tan(THREE.MathUtils.degToRad(15));
    camera.fov = 30;
    camera.position.set(0, 0, z);
    camera.near = 10;
    camera.far = z + 6000;
    camera.updateProjectionMatrix();
  }, [get, size.height]);
  return null;
}

class Guard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function GalaxyCanvas({ onScreen, pointer, ripples }: { onScreen: boolean; pointer: RefObject<GalaxyPointer>; ripples: RefObject<Ripple[]> }) {
  return (
    <Guard>
      <Canvas
        tabIndex={-1}
        dpr={[1, 1.5]}
        resize={{ offsetSize: true, scroll: false }}
        frameloop={onScreen ? "always" : "never"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        <PixelCamera />
        <Field onScreen={onScreen} pointer={pointer} ripples={ripples} />
      </Canvas>
    </Guard>
  );
}
