"use client";

import Link from "next/link";
import { useSlidingPill } from "@/lib/use-sliding-pill";
import type { Icon } from "@/lib/icons";
import { cn } from "@/lib/utils";

export type PillItem<V extends string> = {
  value: V;
  label: string;
  icon?: Icon;
  /** A count shown after the label; `alert` draws it filled (something waits). */
  count?: number;
  alert?: boolean;
  /** A link instead of a button: the strip is then a navigation. */
  href?: string;
};

/**
 * Every row of tabs or choices in Checky: the segmented switch whose ink pill slides to the
 * current item and follows the pointer and the keyboard (lib/use-sliding-pill.ts), as in the top
 * bar. `kind` says what it is for screen readers: `tabs` (a tablist), `radio` (one choice among a
 * few) or `nav` (links to pages, the current one marked `aria-current`).
 */
export function PillTabs<V extends string>({
  value,
  onChange,
  items,
  label,
  kind = "tabs",
  size = "md",
  fill = false,
  className,
}: {
  value: V;
  onChange?: (v: V) => void;
  items: PillItem<V>[];
  label: string;
  kind?: "tabs" | "radio" | "nav";
  /** `sm` 32 px (a small switch), `md` 40 px (the desk's tabs). */
  size?: "sm" | "md";
  /** Items share the width equally. */
  fill?: boolean;
  className?: string;
}) {
  const { host, pill, handlers } = useSlidingPill<HTMLDivElement>(value);
  const role = kind === "tabs" ? "tablist" : kind === "radio" ? "radiogroup" : undefined;
  const strip = (
    <div
      ref={host}
      role={role}
      aria-label={kind === "nav" ? undefined : label}
      className={cn("seg", size === "md" && "seg-lg", fill && "seg-fill", className)}
      {...handlers}
    >
      <span ref={pill} className="seg-pill" aria-hidden />
      {items.map((item) => {
        const current = item.value === value;
        const inside = (
          <>
            {item.icon && <item.icon aria-hidden />}
            {item.label}
            {item.count !== undefined && (
              <span className="seg-count" data-alert={item.alert || undefined}>
                {item.count}
              </span>
            )}
          </>
        );
        const common = { "data-pill-item": "", "data-current": current || undefined, className: "seg-item shrink-0" };
        if (item.href) {
          return (
            <Link key={item.value} href={item.href as never} aria-current={current ? "page" : undefined} {...common}>
              {inside}
            </Link>
          );
        }
        return (
          <button
            key={item.value}
            type="button"
            role={kind === "tabs" ? "tab" : kind === "radio" ? "radio" : undefined}
            aria-selected={kind === "tabs" ? current : undefined}
            aria-checked={kind === "radio" ? current : undefined}
            onClick={() => onChange?.(item.value)}
            {...common}
          >
            {inside}
          </button>
        );
      })}
    </div>
  );
  return kind === "nav" ? <nav aria-label={label}>{strip}</nav> : strip;
}
