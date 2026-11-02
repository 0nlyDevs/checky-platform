import { brand } from "@/lib/brand";
import { cn } from "@/lib/utils";

/** The mark: a light above three lines of a message, on an ink tile. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7 shrink-0", className)}>
      <rect width="64" height="64" rx="12" fill="#0a0a0b" />
      <circle cx="21" cy="21" r="8" fill="#f3f2ee" />
      <rect x="34" y="17" width="18" height="5" rx="1" fill="#f3f2ee" />
      <rect x="12" y="35" width="40" height="5" rx="1" fill="#f3f2ee" />
      <rect x="12" y="45" width="27" height="5" rx="1" fill="#f3f2ee" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="font-display text-xl font-extrabold tracking-[-0.04em]">
        {brand.name}
        <em className="quote font-medium" aria-hidden>
          .
        </em>
      </span>
    </span>
  );
}
