import { brand } from "@/lib/brand";
import { cn } from "@/lib/utils";

/** The mark: a case folder with its tab, stamped with the alarm red. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7 shrink-0", className)}>
      <rect width="64" height="64" rx="10" fill="#dcc9a3" />
      <path d="M12 22h14l4-6h22v34a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2z" fill="#141210" />
      <rect x="19" y="31" width="26" height="9" rx="1.5" fill="none" stroke="#c42a20" strokeWidth="3" transform="rotate(-9 32 35.5)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="font-[family-name:var(--font-anton)] text-xl tracking-[0.06em] uppercase">{brand.name}</span>
    </span>
  );
}
