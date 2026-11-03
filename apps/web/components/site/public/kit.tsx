"use client";

import { Select as SelectPrimitive } from "radix-ui";
import type { CSSProperties, ReactNode } from "react";
import {
  IconCaretDown,
  IconCheck,
  IconFacebookLogo,
  IconGlobe,
  IconNewspaper,
  IconRadio,
  IconTiktokLogo,
  IconWhatsappLogo,
  type Icon,
} from "@/lib/icons";
import { useSlidingPill } from "@/lib/use-sliding-pill";
import { cn } from "@/lib/utils";

/** Where a rumour was seen, as the platform's own logo (ink, in the theme's text colour). */
export const ORIGIN_ICON: Record<string, Icon> = {
  whatsapp: IconWhatsappLogo,
  facebook: IconFacebookLogo,
  tiktok: IconTiktokLogo,
  radio: IconRadio,
  press: IconNewspaper,
  other: IconGlobe,
};

/** A string from `t.look` with its *word* in the landing's italic. */
export function Em({ text }: { text: string }) {
  const parts = text.split("*");
  return <>{parts.map((part, i) => (i % 2 ? <em key={i}>{part}</em> : part))}</>;
}

/** A title whose lines rise out of their own mask, once (the landing's reveal). A line may hold an
 *  `<em>`, set in the italic of the landing. */
export function Lines({ lines, className, id, as: Tag = "h1" }: { lines: ReactNode[]; className?: string; id?: string; as?: "h1" | "h2" }) {
  return (
    <Tag id={id} className={cn("lines", className)}>
      {lines.map((line, i) => (
        <span key={i}>
          <span style={{ "--l": i } as CSSProperties}>{line}</span>
        </span>
      ))}
    </Tag>
  );
}

/** The drawn arrow of the desk's Checky hint: it draws itself once, toward the gesture to make. */
export function Doodle({ className, style }: { className?: string; style?: CSSProperties }) {
  return (
    <svg viewBox="0 0 110 96" className={cn("doodle", className)} style={style} aria-hidden>
      <path pathLength={1} d="M4 70 C 22 72, 40 60, 44 42 C 48 22, 26 18, 24 34 C 22 52, 58 58, 76 66 C 92 74, 100 82, 106 92" />
      <path pathLength={1} d="M93 90 L107 93 L104 79" />
    </svg>
  );
}

/** A hand-written note beside the drawn arrow (Cormorant italic, like the desk's hint). */
export function DoodleNote({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <p className={cn("doodle-note", className)} style={style} aria-hidden>
      {children}
    </p>
  );
}

export type Option = { value: string; label: string; hint?: string };

/**
 * The themed dropdown: a round button whose caret sits right after its label, and a floating menu
 * (18 px, the one shadow) with 44 px options and a check on the choice. Radix Select underneath:
 * keyboard, typeahead and screen readers as a native select.
 */
export function ThemedSelect({
  value,
  onValueChange,
  options,
  label,
  icon: Glyph,
  className,
  id,
}: {
  value: string;
  onValueChange: (v: string) => void;
  options: Option[];
  label: string;
  icon?: Icon;
  className?: string;
  id?: string;
}) {
  // Radix refuses an empty value on an item: the empty choice travels as « __all ».
  const wire = (v: string) => (v === "" ? "__all" : v);
  return (
    <SelectPrimitive.Root value={wire(value)} onValueChange={(v) => onValueChange(v === "__all" ? "" : v)}>
      <SelectPrimitive.Trigger
        id={id}
        aria-label={label}
        className={cn(
          "group inline-flex h-12 max-w-full items-center gap-2 rounded-full border border-input bg-card pr-4 pl-5 text-left font-medium text-foreground outline-none transition-colors hover:border-foreground hover:bg-card hover:text-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background data-[state=open]:border-foreground",
          className,
        )}
      >
        {Glyph && <Glyph className="size-5 shrink-0" aria-hidden />}
        <span className="min-w-0 truncate">
          <SelectPrimitive.Value />
        </span>
        <SelectPrimitive.Icon asChild>
          <IconCaretDown className="size-4 shrink-0 transition-transform duration-300 group-data-[state=open]:rotate-180" aria-hidden />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={8}
          align="start"
          className="pub-menu z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width) overflow-y-auto rounded-[18px] border border-border bg-popover p-1.5 text-popover-foreground shadow-(--shadow-float)"
        >
          <SelectPrimitive.Viewport>
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value || "__all"}
                value={wire(o.value)}
                className="relative flex min-h-11 cursor-pointer items-center gap-3 rounded-xl py-2 pr-10 pl-3 text-[0.9375rem] text-foreground outline-none select-none data-[highlighted]:bg-raised data-[highlighted]:text-foreground data-[state=checked]:bg-active data-[state=checked]:font-semibold data-[state=checked]:text-foreground"
              >
                <span className="min-w-0">
                  <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                  {o.hint && <span className="block text-sm font-normal text-muted-foreground">{o.hint}</span>}
                </span>
                <SelectPrimitive.ItemIndicator className="absolute right-3 inline-flex">
                  <IconCheck className="size-4" aria-hidden />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

/**
 * A choice between a few values on the segmented switch: the ink pill slides to the choice and
 * follows the pointer (lib/use-sliding-pill.ts). A radio group for screen readers.
 */
export function PillChoice<V extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: V;
  onChange: (v: V) => void;
  options: { value: V; label: string; icon?: Icon }[];
  label: string;
  className?: string;
}) {
  const { host, pill, handlers } = useSlidingPill<HTMLDivElement>(value);
  return (
    <div ref={host} role="radiogroup" aria-label={label} className={cn("seg seg-lg", className)} {...handlers}>
      <span ref={pill} className="seg-pill" aria-hidden />
      {options.map(({ value: v, label: l, icon: Glyph }) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          data-pill-item
          data-current={value === v || undefined}
          onClick={() => onChange(v)}
          className="seg-item"
        >
          {Glyph && <Glyph aria-hidden />}
          {l}
        </button>
      ))}
    </div>
  );
}
