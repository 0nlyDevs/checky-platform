import { useRef, useState } from "react";
import { Check, Question, Warning, X } from "@phosphor-icons/react";
import { TONES, VERDICTS } from "../content/site";
import { gsap, useGSAP, useReducedMotion } from "../lib/motion";

const ICONS = {
  vrai: Check,
  faux: X,
  trompeur: Warning,
  inverif: Question,
};

export function Verdict() {
  const root = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      if (reduce) return;
      const el = root.current!;
      const items = gsap.utils.toArray<HTMLElement>(".verdict-item");
      const wash = el.querySelector<HTMLElement>(".verdict-wash")!;
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: el,
          start: "top top",
          end: "bottom bottom",
          scrub: 0.5,
          onUpdate: (st) => setActive(Math.min(VERDICTS.length - 1, Math.floor(st.progress * VERDICTS.length))),
        },
      });
      items.forEach((item, i) => {
        const word = item.querySelector(".verdict-word span");
        const icon = item.querySelector(".verdict-icon");
        const copy = item.querySelectorAll(".verdict-line, .verdict-rule");
        const last = i === items.length - 1;
        tl.to(wash, { backgroundColor: VERDICTS[i].wash, duration: 0.45, ease: "none" }, i);
        tl.fromTo(icon, { scale: 0, rotate: -40 }, { scale: 1, rotate: 0, duration: 0.3, ease: "back.out(1.8)" }, i + 0.04);
        tl.fromTo(word, { yPercent: 112 }, { yPercent: 0, duration: 0.34, ease: "power3.out" }, i + 0.06);
        tl.fromTo(copy, { opacity: 0, y: 22 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.06, ease: "power2.out" }, i + 0.2);
        if (!last) {
          tl.to(word, { yPercent: -112, duration: 0.26, ease: "power3.in" }, i + 0.78);
          tl.to(icon, { scale: 0, duration: 0.22, ease: "power2.in" }, i + 0.8);
          tl.to(copy, { opacity: 0, y: -14, duration: 0.2, ease: "power2.in" }, i + 0.76);
        }
      });
    },
    { scope: root, dependencies: [reduce] },
  );

  const jump = (i: number) => () => {
    const el = root.current!;
    const top = el.getBoundingClientRect().top + window.scrollY;
    const span = el.offsetHeight - window.innerHeight;
    const y = top + (span * (i + 0.45)) / VERDICTS.length;
    window.scrollTo({ top: y, behavior: "smooth" });
  };

  return (
    <section ref={root} id="verdict" className="verdict section">
      <div className="verdict-pin">
        <div className="verdict-frame">
          <div className="verdict-wash" />
          <div className="verdict-stage">
            {VERDICTS.map((v) => {
              const Icon = ICONS[v.key];
              return (
                <div className="verdict-item" key={v.key}>
                  <div>
                    <span className="verdict-icon" style={{ background: TONES[v.key] }}>
                      <Icon size={34} weight="bold" />
                    </span>
                    <div className="display verdict-word">
                      <span>{v.word}</span>
                    </div>
                    <p className="verdict-line">{v.line}</p>
                    <p className="verdict-rule mono">{v.rule}</p>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="verdict-legend" aria-hidden>
            {VERDICTS.map((v, i) => (
              <button key={v.key} type="button" className={i === active ? "is-active" : ""} onClick={jump(i)} tabIndex={-1}>
                <i style={{ background: TONES[v.key] }} />
                <span>{v.word}</span>
              </button>
            ))}
          </div>
          <div className="verdict-foot mono">Quatre réponses, jamais une cinquième. Le pourcentage vient des preuves.</div>
        </div>
      </div>
    </section>
  );
}
