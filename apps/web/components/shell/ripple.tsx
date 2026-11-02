"use client";

import { useEffect } from "react";

const PRESSABLE = '[data-slot="button"], [data-ripple]';

/**
 * Ripple on press for buttons, tabs, the dock and the Checky button: one pointerdown listener for
 * the whole page, a circle in the control's own colour (scale 0 to 1, opacity .24 to 0, 650 ms).
 * Nothing under reduced motion.
 */
export function RippleListener() {
  useEffect(() => {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)");
    const press = (e: PointerEvent) => {
      if (reduce.matches || e.button !== 0) return;
      const el = (e.target as Element | null)?.closest<HTMLElement>(PRESSABLE);
      if (!el || el.matches(":disabled, [aria-disabled=true]")) return;
      const r = el.getBoundingClientRect();
      const size = Math.hypot(r.width, r.height) * 2;
      if (getComputedStyle(el).position === "static") el.style.position = "relative";
      // The circle is clipped by its own frame, so labels that slide out of a control (the dock's
      // flags, the Checky button's label) are never cut.
      const frame = document.createElement("span");
      frame.setAttribute("aria-hidden", "true");
      frame.style.cssText = "position:absolute;inset:0;overflow:hidden;border-radius:inherit;pointer-events:none";
      const s = document.createElement("span");
      s.style.cssText = "position:absolute;border-radius:50%;background:currentColor;opacity:.24;transform:scale(0)";
      s.style.width = s.style.height = `${size}px`;
      s.style.left = `${e.clientX - r.left - el.clientLeft - size / 2}px`;
      s.style.top = `${e.clientY - r.top - el.clientTop - size / 2}px`;
      frame.appendChild(s);
      el.appendChild(frame);
      const a = s.animate([{ transform: "scale(0)", opacity: 0.24 }, { transform: "scale(1)", opacity: 0 }], {
        duration: 650,
        easing: "cubic-bezier(.22,1,.36,1)",
      });
      a.onfinish = a.oncancel = () => frame.remove();
    };
    addEventListener("pointerdown", press, { passive: true });
    return () => removeEventListener("pointerdown", press);
  }, []);
  return null;
}
