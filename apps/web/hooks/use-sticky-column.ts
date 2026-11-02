"use client";

import { useCallback } from "react";
import { stickyTop } from "@/lib/sticky";

/** The shell's top bar marks itself `data-desk-bar`; without one the column sticks to the viewport top. */
function barHeight() {
  const bar = document.querySelector<HTMLElement>("[data-desk-bar]");
  if (!bar) return 0;
  const { position } = getComputedStyle(bar);
  return position === "sticky" || position === "fixed" ? bar.getBoundingClientRect().bottom : 0;
}

/**
 * A side column that rides with the page from 1101 px: it sticks under the bar while it fits, and
 * by its bottom edge once it is taller than the screen. The element also needs `position: sticky`
 * and `align-self: start` in CSS for the widths where the grid really has two columns.
 * `top` is recomputed on resize and whenever the column's own size changes.
 */
export function useStickyColumn<T extends HTMLElement>() {
  // A callback ref: the column may only appear after its data has loaded.
  return useCallback((el: T | null) => {
    if (!el) return;
    const place = () => {
      el.style.top = window.innerWidth > 1100 ? `${stickyTop(barHeight(), window.innerHeight, el.offsetHeight)}px` : "";
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(el);
    window.addEventListener("resize", place);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", place);
    };
  }, []);
}
