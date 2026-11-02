"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { NavItem } from "@/components/shell/nav";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { IconCaretDown, IconDotsThree } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";
import { foldTabs } from "@/lib/priority-nav";

type Tab = NavItem & { href: string };

/** Marks the one tab whose label reads ink on the paper pill (`data-lit`), or none. */
function light(list: HTMLElement | null, lit: HTMLElement | null) {
  list?.querySelectorAll<HTMLElement>(".tab").forEach((tab) => tab.toggleAttribute("data-lit", tab === lit));
}

/** The tabs a workspace shows, with their addresses and the one that is lit. */
export function useTabs(ws: string | undefined, items: NavItem[]) {
  const pathname = usePathname();
  const tabs: Tab[] = ws ? items.filter((i) => i.path).map((i) => ({ ...i, href: `/w/${ws}/${i.path}` })) : [];
  // Analyser lives inside Vérifier now: its old address still lights Vérifier.
  const active = tabs.findIndex(
    (tab) => pathname.startsWith(tab.href) || (tab.path === "verifier" && !!ws && pathname.startsWith(`/w/${ws}/analyser`)),
  );
  return { tabs, active };
}

/**
 * The ink tab island in the middle of the bar, with a paper pill sliding under the current tab.
 * Priority+: the tabs that do not fit fold into « Plus » from the end; a folded current tab gives
 * « Plus » its name and the pill. A hidden row measures every tab so the fold never guesses.
 */
export function TabIsland({ ws, items }: { ws?: string; items: NavItem[] }) {
  const { tabs, active } = useTabs(ws, items);
  const wrap = useRef<HTMLDivElement>(null);
  const ghost = useRef<HTMLDivElement>(null);
  const island = useRef<HTMLUListElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  // Where the pill was last put, and for which tab.
  const last = useRef<{ tab: number; x: number; w: number } | null>(null);
  // The frame that keeps the lit label under the sliding pill (0 when the pill rests).
  const follow = useRef(0);
  const [visible, setVisible] = useState(tabs.length);
  useEffect(() => () => cancelAnimationFrame(follow.current), []);

  // The pill follows the current tab (or « Plus » when it holds it): transform + width, 0.5 s.
  // It slides only when the current tab changes; when its own tab moves (first paint, fonts, a
  // resize that folds it into « Plus ») it is put there at once, as in the mockup.
  const place = useCallback(() => {
    const el = island.current?.querySelector<HTMLElement>("[data-current]");
    const p = pill.current;
    if (!p) return;
    if (!el) {
      p.style.opacity = "0";
      last.current = null;
      light(island.current, null);
      return;
    }
    // the tab is measured inside the list, the pill inside the island: add the island's padding
    const x = el.offsetLeft + (island.current?.offsetLeft ?? 0);
    const w = el.offsetWidth;
    const prev = last.current;
    if (prev && prev.tab === active && prev.x === x && prev.w === w) {
      if (!follow.current) light(island.current, el);
      return;
    }
    const instant = !prev || prev.tab === active;
    if (instant) p.style.transition = "none";
    p.style.opacity = "1";
    p.style.width = `${w}px`;
    p.style.transform = `translateX(${x}px)`;
    cancelAnimationFrame(follow.current);
    follow.current = 0;
    if (instant) {
      void p.offsetWidth;
      p.style.transition = "";
      light(island.current, el);
    } else {
      // The ink label belongs on the paper: a tab is lit only while the pill sits under its centre,
      // so a label never turns ink over the ink island ahead of the sliding pill.
      const step = () => {
        const list = island.current;
        if (!list) return;
        const r = p.getBoundingClientRect();
        if (p.getAnimations().length) {
          const under = Array.from(list.querySelectorAll<HTMLElement>(".tab")).find((tab) => {
            const c = tab.getBoundingClientRect();
            return r.left <= c.left + c.width / 2 && c.left + c.width / 2 <= r.right;
          });
          light(list, under ?? null);
          follow.current = requestAnimationFrame(step);
        } else {
          light(list, list.querySelector<HTMLElement>("[data-current]"));
          follow.current = 0;
        }
      };
      follow.current = requestAnimationFrame(step);
    }
    last.current = { tab: active, x, w };
    // from now on the pill carries the current tab; before, the tab paints its own paper
    p.parentElement?.setAttribute("data-pill", "");
  }, [active]);

  const fit = useCallback(() => {
    const room = wrap.current?.clientWidth ?? 0;
    const cells = ghost.current ? Array.from(ghost.current.children) as HTMLElement[] : [];
    if (!room || cells.length < tabs.length + 1) return;
    const gap = 2;
    const widths = cells.slice(0, tabs.length).map((c) => c.offsetWidth + gap);
    const plain = cells[tabs.length].offsetWidth + gap;
    // the island's own padding (5 px each side) is not room for tabs
    let fold = foldTabs(widths, room - 10, plain, active);
    if (fold.activeFolded && cells[tabs.length + 1]) {
      // « Plus » then carries the current tab's name: measure that label instead
      fold = foldTabs(widths, room - 10, cells[tabs.length + 1].offsetWidth + gap, active);
    }
    setVisible(fold.visible);
    place();
  }, [tabs.length, active, place]);

  useLayoutEffect(() => {
    fit();
    const ro = new ResizeObserver(fit);
    if (wrap.current) ro.observe(wrap.current);
    document.fonts?.ready.then(fit);
    return () => ro.disconnect();
  }, [fit]);

  const folded = tabs.slice(visible);
  const holds = active >= visible;
  useLayoutEffect(place);

  if (!tabs.length) return <div ref={wrap} className="tab-wrap" />;
  const current = active >= 0 ? tabs[active] : undefined;
  const HeldIcon = current?.icon;

  return (
    <div ref={wrap} className="tab-wrap">
      <nav aria-label={t.nav.main} className="tab-island">
        <span ref={pill} className="tab-pill" aria-hidden />
        <ul ref={island} className="tab-list">
          {tabs.slice(0, visible).map(({ label, icon: Icon, href }, i) => (
            <li key={href}>
              <Link href={href} className="tab" data-ripple data-current={i === active || undefined} aria-current={i === active ? "page" : undefined}>
                <Icon className="tab-icon" aria-hidden />
                {label}
              </Link>
            </li>
          ))}
          {folded.length > 0 && (
            <li>
              <DropdownMenu>
                <DropdownMenuTrigger className="tab" data-ripple data-current={holds || undefined} aria-label={holds && current ? `${current.label}, ${t.nav.more}` : undefined}>
                  {holds && HeldIcon ? <HeldIcon className="tab-icon" aria-hidden /> : null}
                  {holds && current ? current.label : t.nav.more}
                  <IconCaretDown className="tab-caret" aria-hidden />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" sideOffset={10} className="tab-menu" aria-label={t.nav.moreLabel}>
                  {folded.map(({ label, icon: Icon, href }, i) => (
                    <DropdownMenuItem key={href} asChild>
                      <Link href={href} aria-current={visible + i === active ? "page" : undefined}>
                        <Icon aria-hidden />
                        {label}
                      </Link>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          )}
        </ul>
      </nav>
      {/* The measuring row: every tab, « Plus », and « Plus » holding the current tab. */}
      <div ref={ghost} className="tab-ghost" aria-hidden inert>
        {tabs.map(({ label, icon: Icon, href }) => (
          <span key={href} className="tab">
            <Icon className="tab-icon" />
            {label}
          </span>
        ))}
        <span className="tab">
          {t.nav.more}
          <IconCaretDown className="tab-caret" />
        </span>
        {current && HeldIcon && (
          <span className="tab">
            <HeldIcon className="tab-icon" />
            {current.label}
            <IconCaretDown className="tab-caret" />
          </span>
        )}
      </div>
    </div>
  );
}

/** Under 640 px the island becomes the ink bar at the thumb: four places, then « Plus ». */
export function TabBar({ ws, items }: { ws?: string; items: NavItem[] }) {
  const { tabs, active } = useTabs(ws, items);
  if (!tabs.length) return null;
  const room = tabs.length > 5 ? 4 : tabs.length;
  const folded = tabs.slice(room);
  const holds = active >= room;
  const current = active >= 0 ? tabs[active] : undefined;
  return (
    <nav aria-label={t.nav.main} className="tab-bar">
      <ul style={{ gridTemplateColumns: `repeat(${room + (folded.length ? 1 : 0)}, minmax(0, 1fr))` }}>
        {tabs.slice(0, room).map(({ label, short, icon: Icon, href }, i) => (
          <li key={href}>
            <Link href={href} className="tab-bar-item" data-ripple aria-current={i === active ? "page" : undefined}>
              <Icon className="size-[22px]" aria-hidden />
              <span>{short ?? label}</span>
            </Link>
          </li>
        ))}
        {folded.length > 0 && (
          <li>
            <DropdownMenu>
              <DropdownMenuTrigger className="tab-bar-item" data-ripple data-current={holds || undefined}>
                {holds && current ? <current.icon className="size-[22px]" aria-hidden /> : <IconDotsThree className="size-[22px]" aria-hidden />}
                <span>{holds && current ? (current.short ?? current.label) : t.nav.more}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="end" sideOffset={10} className="tab-menu" aria-label={t.nav.moreLabel}>
                {folded.map(({ label, icon: Icon, href }, i) => (
                  <DropdownMenuItem key={href} asChild>
                    <Link href={href} aria-current={room + i === active ? "page" : undefined}>
                      <Icon aria-hidden />
                      {label}
                    </Link>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </li>
        )}
      </ul>
    </nav>
  );
}

