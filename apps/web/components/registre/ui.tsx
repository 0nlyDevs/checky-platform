import { cn } from "@/lib/utils";

/** Fields of the registry and figures forms: white card, 1 px stroke, ink focus. */
export const fieldClass =
  "mt-1 w-full rounded-md border border-input bg-card px-3 py-2.5 text-base outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15";

/** A small square tag (« démo », « Scellé », « ancien »); `strong` draws it in ink. */
export function Tag({ children, strong }: { children: React.ReactNode; strong?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-xs font-bold",
        strong ? "border-foreground" : "border-border text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
