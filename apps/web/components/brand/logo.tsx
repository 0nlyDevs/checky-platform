import { brand } from "@/lib/brand";
import { cn } from "@/lib/utils";

/** The mark: « C. » in paper on an ink tile, the wordmark's initial and its dot (as the app icons). */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7 shrink-0", className)}>
      <rect width="64" height="64" rx="14" fill="#0a0a0b" />
      <path d="M38.6 22.2A14 14 0 1 0 38.6 41.8" fill="none" stroke="#f3f2ee" strokeWidth="7.5" strokeLinecap="round" />
      <circle cx="47" cy="42.5" r="4.6" fill="#f3f2ee" />
    </svg>
  );
}

export function Wordmark({ className, mark = true }: { className?: string; mark?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      {mark && <LogoMark />}
      <span className="font-display text-xl font-extrabold tracking-[-0.04em]">
        {brand.name}
        <em className="quote font-medium" aria-hidden>
          .
        </em>
      </span>
    </span>
  );
}
