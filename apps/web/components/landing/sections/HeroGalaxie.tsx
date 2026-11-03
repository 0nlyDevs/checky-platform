import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { GALAXIE } from "../content/hero";
import { ROUTES } from "../content/site";
import { gsap, useGSAP, useReducedMotion } from "../lib/motion";
import { INTRO, introClock, fastForwardIntro } from "../lib/intro";
import { GalaxyCanvas, type GalaxyPointer, type Ripple } from "../three/Galaxy";
import { HeroWordmark } from "../parts/HeroWordmark";
import { rulerFlies } from "../lib/ruler";
import { HERO_PHASE, heroScroll } from "../lib/heroScroll";
import "../styles/hero-galaxie.css";

const HIDDEN = { autoAlpha: 0, y: 28, filter: "blur(8px)" };
const SHOWN = { autoAlpha: 1, y: 0, filter: "blur(0px)", duration: 0.9, ease: "power3.out", stagger: 0.08 };

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * The field in the middle of the hero: the public « Est-ce déjà vérifié ? ».
 * While it is empty and unfocused, real rumours type themselves in and each
 * one "sent" stirs the galaxy; what the visitor types opens /verifies with
 * their text, where the check runs at once.
 */
function PromptBar({ live, onSend }: { live: boolean; onSend: () => void }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [demo, setDemo] = useState({ text: GALAXIE.prompts[0], typing: false });
  const send = useRef(onSend);
  useEffect(() => {
    send.current = onSend;
  });
  const idle = live && !focused && !value;
  useEffect(() => {
    if (!idle) return;
    let i = 0;
    let n = 0;
    let dir = 1;
    let timer = 0;
    const step = () => {
      const p = GALAXIE.prompts[i];
      if (dir > 0) {
        n++;
        if (n >= p.length) {
          setDemo({ text: p, typing: false });
          send.current();
          dir = -1;
          timer = window.setTimeout(step, 2600);
          return;
        }
        setDemo({ text: p.slice(0, n), typing: true });
        timer = window.setTimeout(step, 34 + Math.random() * 40);
      } else {
        n = Math.max(0, n - 3);
        setDemo({ text: p.slice(0, n), typing: false });
        if (n === 0) {
          dir = 1;
          i = (i + 1) % GALAXIE.prompts.length;
          timer = window.setTimeout(step, 420);
          return;
        }
        timer = window.setTimeout(step, 16);
      }
    };
    timer = window.setTimeout(step, 600);
    return () => window.clearTimeout(timer);
  }, [idle]);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = value.trim();
    if (text.length < 3) return input.current?.focus();
    router.push(ROUTES.check(text));
  };
  const lit = value.trim().length >= 3 || (idle && !!demo.text && !demo.typing);
  return (
    <form className="hg-bar" onSubmit={submit} role="search">
      <span className="hg-bar-plus" aria-hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </span>
      <span className="hg-bar-field">
        <input
          ref={input}
          className="hg-bar-input"
          value={value}
          maxLength={6000}
          aria-label={GALAXIE.bar.label}
          placeholder={idle ? "" : GALAXIE.bar.label}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />
        {idle && (
          <span className="hg-bar-demo" aria-hidden>
            {demo.text}
            {demo.typing && <span className="hg-caret" />}
          </span>
        )}
      </span>
      <button type="submit" className={`hg-bar-send${lit ? " is-sent" : ""}`} aria-label={GALAXIE.bar.submit}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M12 19V5M5 12l7-7 7 7" />
        </svg>
      </button>
    </form>
  );
}

export function HeroGalaxie({ ready }: { ready: boolean }) {
  const root = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const pointer = useRef<GalaxyPointer>({ x: 0, y: 0, active: false, clicks: 0 });
  const ripples = useRef<Ripple[]>([]);
  const [onScreen, setOnScreen] = useState(true);
  const [canRender, setCanRender] = useState(false);
  const [barLive, setBarLive] = useState(false);
  const reduce = useReducedMotion();

  // Pointer over the stage: position (centred, y up), hover and clicks.
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const at = (e: PointerEvent) => {
      // The stage shrinks into a frame on scroll: map back to its own pixels.
      const r = el.getBoundingClientRect();
      const k = el.offsetWidth ? r.width / el.offsetWidth : 1;
      pointer.current.x = (e.clientX - r.left - r.width / 2) / k;
      pointer.current.y = -(e.clientY - r.top - r.height / 2) / k;
    };
    const move = (e: PointerEvent) => {
      at(e);
      pointer.current.active = true;
    };
    const leave = () => {
      pointer.current.active = false;
    };
    const down = (e: PointerEvent) => {
      at(e);
      pointer.current.clicks++;
      ripples.current.push({ x: pointer.current.x, y: pointer.current.y, start: -1 });
      if (ripples.current.length > 8) ripples.current.shift();
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    el.addEventListener("pointercancel", leave);
    el.addEventListener("pointerdown", down);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      el.removeEventListener("pointercancel", leave);
      el.removeEventListener("pointerdown", down);
    };
  }, []);

  useEffect(() => {
    if (reduce || !webglAvailable()) return;
    let raf = 0;
    const wait = () => {
      if (document.hidden) raf = requestAnimationFrame(wait);
      else setCanRender(true);
    };
    raf = requestAnimationFrame(wait);
    return () => cancelAnimationFrame(raf);
  }, [reduce]);

  // Scroll state for the 3D scene, and where the picked card must land: the
  // reel slot at the start of « La rumeur ». While that section is still
  // rising, the slot's final place (once its track is stuck) is used, so the
  // card waits exactly where the slot arrives. The fixed canvas only renders
  // while the pin runs or the slot is on screen.
  useEffect(() => {
    const el = stage.current;
    const section = root.current;
    if (!el || !section) return;
    let shown = true;
    const tick = () => {
      const vh = window.innerHeight;
      const vw = window.innerWidth;
      const pinLen = Math.max(1, section.offsetHeight - vh);
      const y = window.scrollY;
      heroScroll.p = Math.max(0, Math.min(1, y / pinLen));
      const slotEl = document.querySelector<HTMLElement>("[data-reel-slot]");
      const track = slotEl?.closest<HTMLElement>("[data-reel-track]");
      let onSlot = false;
      if (slotEl && track) {
        const r = slotEl.getBoundingClientRect();
        const tt = track.getBoundingClientRect().top;
        // Use the rect the card is drawn on (the slot's final place while the
        // section rises), not the slot itself: the slot is still below the
        // screen right after the pin, and hiding the canvas then made the card
        // freeze, vanish and pop back.
        const at = tt > 0 ? new DOMRect(r.left, r.top - tt, r.width, r.height) : r;
        heroScroll.slot = at;
        onSlot = at.right > 0 && at.left < vw && at.bottom > 0 && at.top < vh;
        const live = canRender && heroScroll.p >= HERO_PHASE.pickEnd;
        if (live !== (slotEl.dataset.live === "1")) slotEl.dataset.live = live ? "1" : "";
      } else heroScroll.slot = null;
      const next = !document.hidden && (y < pinLen + 2 || onSlot);
      if (next !== shown) {
        shown = next;
        el.style.visibility = next ? "" : "hidden";
        setOnScreen(next);
      }
    };
    tick();
    gsap.ticker.add(tick);
    return () => {
      gsap.ticker.remove(tick);
      heroScroll.p = 0;
      heroScroll.slot = null;
    };
  }, [canRender]);

  // Master intro clock: starts once the preloader has left.
  useEffect(() => {
    if (reduce) {
      introClock.t = 999;
      introClock.done = true;
      return;
    }
    introClock.t = 0;
    introClock.scale = 1;
    introClock.done = false;
    if (!ready) return;
    const skip = () => fastForwardIntro();
    const on = () => {
      window.addEventListener("wheel", skip, { passive: true });
      window.addEventListener("pointerdown", skip, { passive: true });
      window.addEventListener("keydown", skip);
      window.addEventListener("touchstart", skip, { passive: true });
    };
    const off = () => {
      window.removeEventListener("wheel", skip);
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
      window.removeEventListener("touchstart", skip);
    };
    on();
    const tick = (_: number, dt: number) => {
      introClock.t += (Math.min(dt, 100) / 1e3) * introClock.scale;
      if (!introClock.done && introClock.t > INTRO.cardsAt + 3) {
        introClock.done = true;
        off();
      }
    };
    gsap.ticker.add(tick);
    return () => {
      gsap.ticker.remove(tick);
      off();
      introClock.t = 999;
    };
  }, [ready, reduce]);

  // Copy stack: blur-up reveal once the clock passes copyAt.
  useGSAP(
    () => {
      const items = gsap.utils.toArray<HTMLElement>("[data-hg-reveal]");
      if (reduce) {
        gsap.set(items, { clearProps: "all" });
        return;
      }
      gsap.set(items, HIDDEN);
      if (!ready) return;
      const wait = () => {
        if (introClock.t < INTRO.copyAt) return;
        gsap.ticker.remove(wait);
        gsap.to(items, SHOWN);
        setBarLive(true);
      };
      gsap.ticker.add(wait);
      return () => gsap.ticker.remove(wait);
    },
    { scope: root, dependencies: [ready, reduce] },
  );

  // A sent rumour sends a ripple through the galaxy, from the bar outwards.
  const stir = () => {
    if (heroScroll.p > 0.02) return;
    ripples.current.push({ x: 0, y: 0, start: -1 });
    if (ripples.current.length > 8) ripples.current.shift();
  };

  // Scroll: the copy leaves first (the wordmark flies to the ruler, or leaves
  // with the copy where there is no ruler); the 3D scene does the rest.
  useGSAP(
    () => {
      if (reduce) return;
      const leaving = rulerFlies() ? ".hg-mid, .hg-bottom, .hg-word-blur" : ".hg-mid, .hg-bottom, .hg-word-blur, .hg-word";
      gsap
        .timeline({ scrollTrigger: { trigger: root.current, start: "top top", end: "bottom bottom", scrub: true } })
        .to(leaving, { autoAlpha: 0, y: -36, filter: "blur(6px)", duration: HERO_PHASE.copyEnd, ease: "power1.in" }, 0)
        .to({}, { duration: 1 - HERO_PHASE.copyEnd });
    },
    { scope: root, dependencies: [reduce] },
  );

  return (
    <section ref={root} id="checky" className="hero hero-galaxie">
      <div className="hg-pin" data-pin>
        <div ref={stage} aria-hidden className="hg-canvas">
          {canRender && <GalaxyCanvas onScreen={onScreen} pointer={pointer} ripples={ripples} />}
        </div>

        <div className="hg-layout">
          <div className="hg-top">
            <div className="hg-word-wrap">
              <HeroWordmark word={GALAXIE.word} reduce={reduce} />
            </div>
          </div>

          <div className="hg-mid">
            <span className="hg-tag" data-hg-reveal>
              {GALAXIE.tag}
            </span>
            <div className="hg-bar-wrap" data-hg-reveal>
              <PromptBar live={barLive && !reduce} onSend={stir} />
            </div>
          </div>

          <div className="hg-bottom">
            <h1 className="hg-h1" data-hg-reveal>
              {GALAXIE.title} <em>{GALAXIE.titleEm}</em>
            </h1>
            <p className="hg-lead" data-hg-reveal>
              {GALAXIE.lead}
            </p>
            <div className="hg-actions" data-hg-reveal>
              <Link className="btn btn-fill" href={GALAXIE.primary.href}>
                {GALAXIE.primary.label} <span className="arrow">↗</span>
              </Link>
              <div className="hg-partners">
                <span className="hg-partners-label">{GALAXIE.partners.label}</span>
                <ul>
                  {GALAXIE.partners.logos.map((l) => (
                    <li key={l.src}>
                      <a href={l.href} target="_blank" rel="noreferrer" title={l.name}>
                        <Image src={l.src} alt={l.name} width={l.width} height={l.height} />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
