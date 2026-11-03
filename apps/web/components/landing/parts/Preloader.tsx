import { useRef } from "react";
import { gsap, ScrollTrigger, useGSAP, getLenis, useReducedMotion } from "../lib/motion";

export function Preloader({ onDone }: { onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      const el = ref.current!;
      const num = el.querySelector<HTMLElement>(".pre-num")!;
      const lenis = getLenis();
      lenis?.stop();
      document.documentElement.style.overflow = "hidden";
      const finish = () => {
        el.style.display = "none";
        document.documentElement.style.overflow = "";
        lenis?.start();
        ScrollTrigger.refresh();
        onDone();
      };
      if (reduce) {
        finish();
        return;
      }
      const counter = { v: 0 };
      const tl = gsap.timeline({ paused: true, onComplete: finish });
      tl.fromTo(".pre-word .line > span", { yPercent: 112 }, { yPercent: 0, duration: 1, stagger: 0.1, ease: "power4.out" }, 0.15)
        .to(
          counter,
          {
            v: 100,
            duration: 1.7,
            ease: "power2.inOut",
            onUpdate: () => {
              num.textContent = String(Math.round(counter.v)).padStart(3, "0");
            },
          },
          0.15,
        )
        .to(".pre-word .line > span", { yPercent: -112, duration: 0.55, stagger: 0.06, ease: "power3.in" }, ">-0.05")
        .to(".pre-foot", { opacity: 0, duration: 0.3 }, "<")
        .to(el, { yPercent: -100, duration: 0.95, ease: "power4.inOut" }, ">-0.1");
      let started = false;
      const go = () => {
        if (started) return;
        started = true;
        tl.play();
      };
      document.fonts.ready.then(go);
      const fallback = window.setTimeout(go, 1500);
      return () => window.clearTimeout(fallback);
    },
    { scope: ref, dependencies: [reduce] },
  );

  return (
    <div ref={ref} className="pre" aria-hidden>
      <h2 className="pre-word display lines">
        <span className="line">
          <span>Marina sa</span>
        </span>
        <span className="line">
          <span>sandoka ?</span>
        </span>
      </h2>
      <div className="pre-foot">
        <span className="mono">Checky, la torche du journaliste</span>
        <span className="pre-num">000</span>
      </div>
    </div>
  );
}
