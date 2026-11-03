"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

const ITEM = "[data-pill-item]";

/** Marks the one item whose label reads on the pill (`data-lit`), or none. */
function light(host: HTMLElement | null, lit: HTMLElement | null) {
  host?.querySelectorAll<HTMLElement>(ITEM).forEach((item) => item.toggleAttribute("data-lit", item === lit));
}

/** An element's left edge inside `ancestor` (the pill's offset parent), through every offset parent between. */
function leftWithin(el: HTMLElement, ancestor: Element | null): number {
  let x = 0;
  let node: HTMLElement | null = el;
  while (node && node !== ancestor) {
    x += node.offsetLeft;
    node = node.offsetParent as HTMLElement | null;
  }
  return x;
}

/**
 * The pill that slides under a row of places: the desk's tab island, the public bar, the language
 * switch, the filters. It rests under the current item (`data-current`), follows the pointer and the
 * keyboard while they are over another item (`data-pill-item`), and comes back when they leave. A
 * click needs nothing more: the pill is already under the item, which becomes current.
 *
 * The pill slides (CSS transition on transform and width) when it moves to another item, and is put
 * in place at once when its own item moves (first paint, fonts, a resize). While it slides, only the
 * item under its centre is lit, so a label never turns ink over the ink island ahead of the pill.
 * `key` changes when the current item does (the route, the selected value).
 */
export function useSlidingPill<H extends HTMLElement = HTMLElement>(key: unknown) {
  const host = useRef<H>(null);
  const pill = useRef<HTMLSpanElement>(null);
  // The item the pointer or the keyboard is on, when it is not the current one.
  const target = useRef<HTMLElement | null>(null);
  // Where the pill was last put, and under which item.
  const last = useRef<{ el: HTMLElement; x: number; w: number } | null>(null);
  // The frame that keeps the lit label under the sliding pill (0 when the pill rests).
  const follow = useRef(0);
  useEffect(() => () => cancelAnimationFrame(follow.current), []);

  const place = useCallback(() => {
    const list = host.current;
    const p = pill.current;
    if (!list || !p) return;
    const hovered = target.current && list.contains(target.current) ? target.current : null;
    const el = hovered ?? list.querySelector<HTMLElement>(`${ITEM}[data-current]`);
    if (!el) {
      p.style.opacity = "0";
      last.current = null;
      cancelAnimationFrame(follow.current);
      follow.current = 0;
      light(list, null);
      return;
    }
    const x = leftWithin(el, p.offsetParent);
    const w = el.offsetWidth;
    const prev = last.current;
    if (prev && prev.el === el && prev.x === x && prev.w === w) {
      if (!follow.current) light(list, el);
      return;
    }
    const instant = !prev || prev.el === el;
    if (instant) p.style.transition = "none";
    p.style.opacity = "1";
    p.style.width = `${w}px`;
    p.style.transform = `translateX(${x}px)`;
    cancelAnimationFrame(follow.current);
    follow.current = 0;
    if (instant) {
      void p.offsetWidth;
      p.style.transition = "";
      light(list, el);
    } else {
      const step = () => {
        const r = p.getBoundingClientRect();
        if (p.getAnimations().length) {
          const under = Array.from(list.querySelectorAll<HTMLElement>(ITEM)).find((item) => {
            const c = item.getBoundingClientRect();
            return r.left <= c.left + c.width / 2 && c.left + c.width / 2 <= r.right;
          });
          light(list, under ?? null);
          follow.current = requestAnimationFrame(step);
        } else {
          light(list, el);
          follow.current = 0;
        }
      };
      follow.current = requestAnimationFrame(step);
    }
    last.current = { el, x, w };
    // From now on the pill carries the current item; before, the item paints its own fill.
    p.parentElement?.setAttribute("data-pill", "");
  }, []);

  // The current item changed (a route, a choice): the pill goes there.
  useLayoutEffect(place, [key, place]);

  // Fonts and resizes move the items under a resting pill.
  useLayoutEffect(() => {
    const list = host.current;
    if (!list) return;
    const ro = new ResizeObserver(() => place());
    ro.observe(list);
    document.fonts?.ready.then(() => place());
    return () => ro.disconnect();
  }, [place]);

  const go = useCallback(
    (el: HTMLElement | null) => {
      if (target.current === el) return;
      target.current = el;
      place();
    },
    [place],
  );

  const handlers = {
    // A finger has no hover: a tap moves the pill through the new current item instead.
    onPointerOver: (e: React.PointerEvent) => {
      if (e.pointerType === "touch") return;
      const item = (e.target as Element).closest<HTMLElement>(ITEM);
      if (item && host.current?.contains(item)) go(item);
    },
    onPointerLeave: (e: React.PointerEvent) => {
      if (e.pointerType !== "touch") go(null);
    },
    // Only the keyboard's focus moves the pill: a mouse click focuses the item it is already under.
    onFocus: (e: React.FocusEvent) => {
      const item = (e.target as Element).closest<HTMLElement>(ITEM);
      if (item && (e.target as Element).matches(":focus-visible")) go(item);
    },
    onBlur: (e: React.FocusEvent) => {
      if (!host.current?.contains(e.relatedTarget as Node | null)) go(null);
    },
  };

  return { host, pill, place, handlers };
}
