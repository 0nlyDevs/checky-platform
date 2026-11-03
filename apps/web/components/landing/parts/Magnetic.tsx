import { useRef, type ReactNode } from "react";
import { gsap, useGSAP, useFinePointer, useReducedMotion } from "../lib/motion";

export function Magnetic({ children, strength = 0.35 }: { children: ReactNode; strength?: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const fine = useFinePointer();
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      if (!fine || reduce) return;
      const el = wrap.current!;
      const inner = el.firstElementChild as HTMLElement | null;
      if (!inner) return;
      const xTo = gsap.quickTo(inner, "x", { duration: 0.4, ease: "power2.out" });
      const yTo = gsap.quickTo(inner, "y", { duration: 0.4, ease: "power2.out" });
      const move = (e: MouseEvent) => {
        const r = el.getBoundingClientRect();
        xTo((e.clientX - r.left - r.width / 2) * strength);
        yTo((e.clientY - r.top - r.height / 2) * strength);
      };
      const leave = () => {
        gsap.to(inner, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.45)" });
      };
      el.addEventListener("mousemove", move);
      el.addEventListener("mouseleave", leave);
      return () => {
        el.removeEventListener("mousemove", move);
        el.removeEventListener("mouseleave", leave);
      };
    },
    { dependencies: [fine, reduce, strength] },
  );

  return (
    <div ref={wrap} className="magnetic">
      {children}
    </div>
  );
}
