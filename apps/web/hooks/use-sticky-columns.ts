"use client";

import { useCallback } from "react";
import { shorterColumn, stickyTop } from "@/lib/sticky";

/** The shell's top bar marks itself `data-desk-bar`; without one the column sticks to the viewport top. */
function barHeight() {
  const bar = document.querySelector<HTMLElement>("[data-desk-bar]");
  if (!bar) return 0;
  const { position } = getComputedStyle(bar);
  return position === "sticky" || position === "fixed" ? bar.getBoundingClientRect().bottom : 0;
}

function set(el: HTMLElement, prop: "position" | "top" | "alignSelf", value: string) {
  if (el.style[prop] !== value) el.style[prop] = value;
}

/**
 * For a grid laid out as two columns side by side: the shorter column rides with the page. It
 * scrolls with the longer one until its bottom comes into view, then stays there, as high as the page
 * ends under the grid so it never jumps at the very end (or under the bar,
 * when it fits the screen) while the longer one goes on. Whichever side is shorter, and only while
 * the grid really shows two columns: on one column nothing sticks. Put the ref on the grid; it is
 * re-measured when the window, the grid or any column changes size, or a column appears.
 */
export function useStickyColumns<T extends HTMLElement>() {
  // A callback ref: the grid may only appear after its data has loaded.
  return useCallback((grid: T | null) => {
    if (!grid) return;
    const children = () =>
      [...grid.children].filter((el): el is HTMLElement => el instanceof HTMLElement && el.offsetParent !== null);

    const place = () => {
      const kids = children();
      const twoColumns = new Set(kids.map((el) => el.offsetLeft)).size === 2;
      // Columns keep their own height (no stretch), otherwise both measure as tall as the row.
      for (const el of kids) set(el, "alignSelf", twoColumns ? "start" : "");
      // offsetLeft/offsetTop ignore the sticky shift, so a stuck column measures as laid out.
      const boxes = kids.map((el) => ({ left: el.offsetLeft, top: el.offsetTop, bottom: el.offsetTop + el.offsetHeight }));
      const index = twoColumns ? shorterColumn(boxes) : null;
      kids.forEach((el, i) => {
        if (i === index) return;
        set(el, "position", "");
        set(el, "top", "");
      });
      if (index === null) return;
      const column = kids[index];
      set(column, "position", "sticky");
      // Its bottom stops where the page ends under the grid, so it does not jump at the very end.
      const below = document.documentElement.scrollHeight - (grid.getBoundingClientRect().bottom + window.scrollY);
      set(column, "top", `${stickyTop(barHeight(), window.innerHeight, column.offsetHeight, Math.max(24, below))}px`);
    };

    const sizes = new ResizeObserver(() => place());
    const watch = () => {
      sizes.disconnect();
      sizes.observe(grid);
      for (const el of children()) sizes.observe(el);
    };
    const mutations = new MutationObserver(() => {
      watch();
      place();
    });
    mutations.observe(grid, { childList: true });
    watch();
    place();
    window.addEventListener("resize", place);
    return () => {
      sizes.disconnect();
      mutations.disconnect();
      window.removeEventListener("resize", place);
    };
  }, []);
}
