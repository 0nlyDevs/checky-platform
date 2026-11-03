import { useEffect, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import Lenis from "lenis";

gsap.registerPlugin(ScrollTrigger, useGSAP);
ScrollTrigger.config({ ignoreMobileResize: true });

let lenis: Lenis | null = null;
const raf = (time: number) => lenis?.raf(time * 1000);

/**
 * Smooth scroll for the landing only. `root` (the landing wrapper) gets the
 * `motion` class its styles key on; `destroyScroll` undoes all of it when
 * the visitor leaves for another page of the app.
 */
export function initScroll(root: HTMLElement) {
  root.classList.add("motion");
  if (lenis) return lenis;
  lenis = new Lenis({
    duration: 1.15,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: true,
    touchMultiplier: 1.6,
  });
  lenis.on("scroll", ScrollTrigger.update);
  gsap.ticker.add(raf);
  gsap.ticker.lagSmoothing(0);
  return lenis;
}

export function destroyScroll(root: HTMLElement | null) {
  root?.classList.remove("motion");
  gsap.ticker.remove(raf);
  gsap.ticker.lagSmoothing(500, 33);
  lenis?.destroy();
  lenis = null;
}

export const getLenis = () => lenis;

export function scrollToId(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  if (lenis) lenis.scrollTo(el, { duration: 1.4, easing: (t) => 1 - Math.pow(1 - t, 4) });
  else el.scrollIntoView({ behavior: "smooth" });
}

const query = "(prefers-reduced-motion: reduce)";

export function useReducedMotion() {
  const [reduce, setReduce] = useState(() => (typeof window !== "undefined" ? window.matchMedia(query).matches : false));
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setReduce(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduce;
}

export function useFinePointer() {
  const [fine, setFine] = useState(() => (typeof window !== "undefined" ? window.matchMedia("(hover: hover) and (pointer: fine)").matches : true));
  useEffect(() => {
    const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
    const on = () => setFine(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return fine;
}

export { gsap, ScrollTrigger, useGSAP };
