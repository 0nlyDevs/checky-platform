import { useRef } from "react";
import { gsap, useGSAP, scrollToId, useReducedMotion } from "../lib/motion";

export function Wordmark() {
  const ref = useRef<HTMLAnchorElement>(null);
  const reduce = useReducedMotion();
  useGSAP(
    () => {
      const el = ref.current!;
      if (reduce) {
        gsap.set(el, { opacity: 1, y: 0 });
        el.classList.add("is-on");
        return;
      }
      gsap.to(el, {
        opacity: 1,
        y: 0,
        duration: 0.6,
        ease: "power3.out",
        scrollTrigger: {
          trigger: "#rumeur",
          start: "top 85%",
          toggleActions: "play none none reverse",
          onToggle: (s) => el.classList.toggle("is-on", s.isActive),
        },
      });
    },
    { dependencies: [reduce] },
  );
  return (
    <a
      ref={ref}
      href="#checky"
      className="wordmark"
      onClick={(e) => {
        e.preventDefault();
        scrollToId("checky");
      }}
    >
      CHECKY
    </a>
  );
}
