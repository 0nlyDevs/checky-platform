"use client";

import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { ChevronLeft } from "lucide-react";
import { type ClaimView, VERDICT_META } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const HOUR = 3_600_000;
const DAY_START = 6; // 06h
const DAY_END = 22; // 22h
const MOBILE_WINDOW_HOURS = 6;

const timeFmt = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
const shortDayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

export function formatTime(d: Date) {
  return timeFmt.format(d);
}

/** "4 h 35", "12 min", "2 j" */
export function formatDuration(ms: number) {
  const min = Math.max(0, Math.round(ms / 60_000));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h >= 48) return `${Math.floor(h / 24)} j`;
  const rest = min % 60;
  return rest ? `${h} h ${String(rest).padStart(2, "0")}` : `${h} h`;
}

function dayRange(now: Date) {
  const start = new Date(now);
  start.setHours(Math.min(DAY_START, now.getHours()), 0, 0, 0);
  const end = new Date(now);
  end.setHours(Math.max(DAY_END, now.getHours() + 1), 0, 0, 0);
  return { start: start.getTime(), end: end.getTime() };
}

type Props = {
  claims: ClaimView[];
  now: Date;
  focusedId: string | null;
  onFocusChange: (id: string | null) => void;
  onSelect: (id: string) => void;
};

export function DayGrid({ claims, now, focusedId, onFocusChange, onSelect }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const nowLine = useRef<HTMLDivElement>(null);
  const { start, end } = dayRange(now);
  const span = end - start;
  const hours = useMemo(() => {
    const list: number[] = [];
    for (let h = start; h <= end; h += HOUR) list.push(h);
    return list;
  }, [start, end]);
  const pct = (ms: number) => ((Math.min(Math.max(ms, start), end) - start) / span) * 100;
  const nowPct = pct(now.getTime());
  const totalHours = span / HOUR;

  const lanes = useMemo(
    () =>
      claims
        .filter((c) => c.firstSeen)
        .sort((a, b) => a.firstSeen!.getTime() - b.firstSeen!.getTime()),
    [claims],
  );

  // Phones see a 6-hour window; open it on "maintenant".
  useLayoutEffect(() => {
    const frame = requestAnimationFrame(() => {
      const el = scroller.current;
      const line = nowLine.current;
      if (!el || !line || el.scrollWidth <= el.clientWidth) return;
      const lineX = line.getBoundingClientRect().left - el.getBoundingClientRect().left + el.scrollLeft;
      el.scrollLeft = lineX - el.clientWidth * 0.82;
    });
    return () => cancelAnimationFrame(frame);
    // Only on first layout; later ticks must not fight the user's scroll.
  }, []);

  // Escape releases the focused block.
  useEffect(() => {
    if (!focusedId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onFocusChange(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusedId, onFocusChange]);

  return (
    <section aria-labelledby="grid-title" className="border-y border-border bg-card lg:rounded-lg lg:border">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 px-4 pt-3.5 lg:px-5">
        <h2 id="grid-title" className="font-display text-base font-semibold tracking-wide uppercase">
          {t.claims.gridLabel}
        </h2>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground" aria-label={t.claims.legend.label}>
          <li className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-[2px] bg-foreground/70" aria-hidden />
            {t.claims.legend.confirmed}
          </li>
          <li className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-[2px] border border-dashed border-verdict-misleading-ink bg-verdict-misleading-soft" aria-hidden />
            {t.claims.legend.suggested}
          </li>
          <li className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-[2px] border border-foreground/60 bg-card" aria-hidden />
            {t.claims.legend.unchecked}
          </li>
        </ul>
      </div>
      <div
        ref={scroller}
        className="overflow-x-auto overscroll-x-contain [scrollbar-width:thin]"
        onMouseLeave={() => onFocusChange(null)}
      >
        <div
          className="relative min-w-full px-4 pt-1 pb-4 lg:!w-full lg:px-5"
          style={{ width: `calc(100% * ${totalHours / MOBILE_WINDOW_HOURS})` }}
        >
          {/* Hour ruler */}
          <div className="relative h-12" aria-hidden>
            {hours.map((h) => {
              const d = new Date(h);
              return (
                <span
                  key={h}
                  className="absolute top-6 -translate-x-1/2 font-display text-sm font-medium tracking-wide text-muted-foreground tabular"
                  style={{ left: `${pct(h)}%` }}
                >
                  {String(d.getHours()).padStart(2, "0")}h
                </span>
              );
            })}
          </div>

          <div className="relative">
            {/* The rest of the day, not yet aired */}
            <div
              aria-hidden
              className="absolute inset-y-0 right-0 bg-muted/60"
              style={{ left: `${nowPct}%` }}
            />
            {/* Hairline hour rules */}
            {hours.map((h) => (
              <div
                key={h}
                aria-hidden
                className="absolute inset-y-0 w-px bg-rule"
                style={{ left: `${pct(h)}%` }}
              />
            ))}

            {lanes.length === 0 ? (
              <p className="relative py-8 text-center text-sm text-muted-foreground">{t.claims.gridHint}</p>
            ) : (
              <ol className="relative space-y-1.5 py-1">
                {lanes.map((c, i) => {
                  const id = c.item.id;
                  const seenDate = c.firstSeen!;
                  const seen = seenDate.getTime();
                  const left = pct(seen);
                  const width = Math.max(nowPct - left, 0.6);
                  const v = c.verdict ?? c.suggested;
                  const meta = v ? VERDICT_META[v] : null;
                  const Icon = meta?.icon;
                  const focused = focusedId === id;
                  const dimmed = focusedId !== null && !focused;
                  // Started before the grid's first hour: say when, so the length stays honest.
                  const before = seen < start;
                  const carried = before
                    ? `${seenDate.toDateString() === now.toDateString() ? "" : shortDayFmt.format(seenDate) + " "}${formatTime(seenDate)}`
                    : null;
                  const labelOutside = width < 16 && !before;
                  const duration = formatDuration(now.getTime() - seen);
                  const label = (
                    <>
                      {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
                      {carried && (
                        <span className="flex shrink-0 items-center font-display font-medium tracking-wide tabular">
                          <ChevronLeft className="-ml-1 size-3.5" aria-hidden />
                          {carried}
                        </span>
                      )}
                      <span className="shrink-0 font-display font-semibold tracking-wide tabular">{c.ref}</span>
                    </>
                  );
                  return (
                    <li
                      key={id}
                      className={cn("relative h-8 transition-opacity duration-200", dimmed && "opacity-40")}
                    >
                      <button
                        type="button"
                        onMouseEnter={() => onFocusChange(id)}
                        onFocus={() => onFocusChange(id)}
                        onBlur={() => onFocusChange(null)}
                        onClick={() => onSelect(id)}
                        aria-label={`${c.ref} — ${c.item.title} — ${meta ? meta.label : t.verdict.none}, circule depuis ${duration}`}
                        className={cn(
                          "absolute inset-y-0 flex origin-left items-center rounded-[3px] text-left outline-none",
                          "animate-[grid-extend_640ms_var(--ease-out-expo)_backwards] transition-[box-shadow,transform] duration-200",
                          !v && "border border-foreground/60 bg-card text-foreground",
                          v && !c.verdict && cn("border border-dashed border-current", meta!.soft, meta!.ink),
                          c.verdict && cn(meta!.fill, meta!.on),
                          focused && "z-10 -translate-y-px shadow-[0_6px_16px_-6px_rgb(15_59_54/0.45)] ring-2 ring-signal",
                          before && "rounded-l-none",
                        )}
                        style={{ left: `${left}%`, width: `${width}%`, animationDelay: `${i * 35}ms` }}
                      >
                      </button>
                      {!labelOutside && (
                        // Outside the button (sticky does not work inside one) and clipped, not scrolled,
                        // so the verdict icon and ref stay in view when the phone window scrolls.
                        <span
                          aria-hidden
                          className={cn(
                            "pointer-events-none absolute inset-y-0 z-10 flex items-center overflow-clip text-sm",
                            !v && "text-foreground",
                            v && !c.verdict && meta!.ink,
                            c.verdict && meta!.on,
                            focused && "-translate-y-px",
                          )}
                          style={{ left: `${left}%`, width: `${width}%` }}
                        >
                          <span className="sticky left-0 flex max-w-[min(100%,80vw)] min-w-0 items-center gap-1.5 px-2">
                            {label}
                            <span className="truncate">{c.item.title}</span>
                          </span>
                        </span>
                      )}
                      {labelOutside && (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute top-1/2 flex -translate-y-1/2 items-center gap-1.5 pr-2 text-sm whitespace-nowrap"
                          style={{ right: `${100 - left}%` }}
                        >
                          {label}
                          <span className="hidden max-w-[16rem] truncate text-muted-foreground md:inline">
                            {c.item.title}
                          </span>
                        </span>
                      )}
                      {nowPct < 92 && (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute top-1/2 -translate-y-1/2 pl-2.5 font-display text-sm font-medium tracking-wide whitespace-nowrap text-muted-foreground tabular"
                          style={{ left: `${nowPct}%` }}
                        >
                          {duration}
                        </span>
                      )}
                      {focused && (
                        <div
                          role="tooltip"
                          className="absolute top-full z-20 mt-1.5 w-[min(26rem,80vw)] rounded-md border border-border bg-popover p-3 text-popover-foreground shadow-[0_10px_28px_-10px_rgb(15_59_54/0.4)] animate-in fade-in-0 slide-in-from-top-1 duration-150"
                          style={left > 55 ? { right: `${100 - nowPct}%` } : { left: `${left}%` }}
                        >
                          <p className="flex items-center gap-2 font-display text-sm font-semibold tracking-wide tabular">
                            {c.ref}
                            <span className="font-sans font-normal text-muted-foreground">
                              vue {carried ? `le ${shortDayFmt.format(seenDate)} à` : "à"} {formatTime(seenDate)}
                              {c.origin ? ` · ${t.origins[c.origin as keyof typeof t.origins] ?? c.origin}` : ""}
                            </span>
                          </p>
                          <p className="mt-1 font-medium text-pretty">{c.item.title}</p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            Circule depuis <span className="font-medium text-foreground tabular">{duration}</span>
                            {" · "}
                            {meta ? `${meta.label}${c.verdict ? "" : ` (${t.verdict.suggested})`}` : t.verdict.none}
                          </p>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}

            {/* Maintenant */}
            <div
              ref={nowLine}
              aria-hidden
              className="pointer-events-none absolute -top-12 bottom-0 z-[5] w-0.5 bg-signal"
              style={{ left: `${nowPct}%` }}
            >
              <span className="absolute top-0 left-1/2 -translate-x-1/2 rounded-sm bg-signal px-1.5 py-0.5 font-display text-xs font-semibold tracking-wider whitespace-nowrap text-[#14201d] uppercase tabular">
                {t.claims.now} {formatTime(now)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
