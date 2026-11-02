"use client";

import { useEffect } from "react";
import { t } from "@/lib/i18n/fr";

/**
 * The case file reacts to reading: pieces enter the folder, report lines clear, stamps land, and the
 * header's status line follows the case. Without script every part is simply there and plain.
 */
export function DossierMotion() {
  useEffect(() => {
    const root = document.querySelector(".site");
    if (!root) return;
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) root.classList.add("motion");
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          const el = e.target as HTMLElement;
          if (el.classList.contains("stamp")) el.dataset.on = "true";
          else el.dataset.in = "true";
          io.unobserve(el);
        }
      },
      { rootMargin: "0px 0px -20% 0px" },
    );
    const watch = (scope: ParentNode) => scope.querySelectorAll("[data-observe]:not([data-in]):not([data-on])").forEach((el) => io.observe(el));
    watch(root);
    // Public pages load their files after the first paint: new ones are watched as they arrive.
    const mo = new MutationObserver(() => watch(root));
    mo.observe(root, { childList: true, subtree: true });
    const status = document.getElementById("case-status");
    const marks: [string, string][] = [
      ["affaire", t.site.status.pieces],
      ["methode", t.site.status.checking],
      ["sorties", t.site.status.verdict],
    ];
    const onScroll = () => {
      let text: string = t.site.status.open;
      for (const [id, label] of marks) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top < innerHeight * 0.4) text = label;
      }
      if (status && status.textContent !== text) status.textContent = text;
    };
    addEventListener("scroll", onScroll, { passive: true });
    return () => {
      io.disconnect();
      mo.disconnect();
      removeEventListener("scroll", onScroll);
    };
  }, []);
  return null;
}
