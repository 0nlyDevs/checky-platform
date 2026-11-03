import { gsap, useGSAP } from "../lib/motion";

const SKIP = ".hero, .rumeur, .pre";

export function useReveals(ready: boolean, reduce: boolean) {
  useGSAP(
    () => {
      if (!ready || reduce) return;
      gsap.utils.toArray<HTMLElement>("[data-lines]").forEach((el) => {
        if (el.closest(SKIP)) return;
        gsap.fromTo(
          el.querySelectorAll(".line > span"),
          { yPercent: 112 },
          { yPercent: 0, duration: 1.05, stagger: 0.09, ease: "power4.out", scrollTrigger: { trigger: el, start: "top 88%", once: true } },
        );
      });
      gsap.utils.toArray<HTMLElement>('[data-reveal="fade"]').forEach((el) => {
        if (el.closest(SKIP)) return;
        gsap.fromTo(
          el,
          { opacity: 0, y: 28 },
          { opacity: 1, y: 0, duration: 0.9, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 90%", once: true } },
        );
      });
      gsap.utils.toArray<HTMLElement>('[data-reveal="stagger"]').forEach((el) => {
        if (el.closest(SKIP)) return;
        gsap.fromTo(
          el.children,
          { opacity: 0, y: 24 },
          { opacity: 1, y: 0, duration: 0.8, stagger: 0.08, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 88%", once: true } },
        );
      });
    },
    { dependencies: [ready, reduce] },
  );
}
