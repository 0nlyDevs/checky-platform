import { useRef } from "react";
import { gsap, useGSAP, useFinePointer, useReducedMotion } from "../lib/motion";

export function Gesture({ title, body, tag }: { title: string; body: string; tag: string }) {
  const root = useRef<HTMLLIElement>(null);
  const fine = useFinePointer();
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      if (!fine || reduce) return;
      const el = root.current!;
      const panel = el.querySelector<HTMLElement>(".gesture-panel")!;
      const row = el.querySelector<HTMLElement>(".gesture-row")!;
      const dir = (e: MouseEvent) => {
        const r = el.getBoundingClientRect();
        return e.clientY < r.top + r.height / 2 ? -101 : 101;
      };
      const enter = (e: MouseEvent) => {
        gsap.killTweensOf([panel, row]);
        gsap.fromTo(panel, { yPercent: dir(e) }, { yPercent: 0, duration: 0.45, ease: "power3.out" });
        gsap.to(row, { opacity: 0.2, duration: 0.3 });
      };
      const leave = (e: MouseEvent) => {
        gsap.killTweensOf([panel, row]);
        gsap.to(panel, { yPercent: dir(e), duration: 0.4, ease: "power3.in" });
        gsap.to(row, { opacity: 1, duration: 0.3 });
      };
      el.addEventListener("mouseenter", enter);
      el.addEventListener("mouseleave", leave);
      return () => {
        el.removeEventListener("mouseenter", enter);
        el.removeEventListener("mouseleave", leave);
      };
    },
    { scope: root, dependencies: [fine, reduce] },
  );

  return (
    <li ref={root} className="gesture">
      <div className="gesture-row">
        <span>{title}</span>
        <span className="gesture-tag mono">{tag}</span>
      </div>
      <p className="gesture-body">{body}</p>
      <div className="gesture-panel" aria-hidden>
        {body}
      </div>
    </li>
  );
}
