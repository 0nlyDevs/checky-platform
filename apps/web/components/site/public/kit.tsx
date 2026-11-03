"use client";

import { type CSSProperties, type ReactNode, useSyncExternalStore } from "react";
import {
  IconFacebookLogo,
  IconGlobe,
  IconNewspaper,
  IconRadio,
  IconTiktokLogo,
  IconWhatsappLogo,
  type Icon,
} from "@/lib/icons";
import { reducedMotion } from "@/lib/prefs";
import { useSlidingPill } from "@/lib/use-sliding-pill";
import { cn } from "@/lib/utils";

/** True in Mode éco, with reduced motion, and on the server: decorative clips then stay off. */
export function useStill(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => reducedMotion(),
    () => true,
  );
}

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

export { type Option, ThemedSelect } from "@/components/ui/select";

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
