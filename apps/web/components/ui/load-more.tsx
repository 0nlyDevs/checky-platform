"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { IconArrowDown, IconCheck, IconCircleNotch, IconWarning } from "@/lib/icons";

export type LoadMoreWords = {
  label: string;
  shown: (n: number, total: number) => string;
  left: (n: number) => string;
  next: (n: number) => string;
  loading: string;
  added: (n: number) => string;
  all: (n: number) => string;
  failed: string;
  retry: string;
};

/**
 * The end of a long list: how far the reader is (an ink rail filling up, « 30 sur 124 »), how much
 * is left, and one button that brings the next page. While it loads the button says so and holds
 * its place; a failure says so and offers to try again; when everything is shown the rail is full
 * and a line says so. Screen readers hear how many rows arrived. Nothing loads by itself: the
 * reader decides, which suits Mode éco and slow connections. Hidden when the list fits one page.
 */
export function LoadMore({
  shown,
  total,
  pageSize,
  hasMore,
  loading,
  failed,
  onMore,
  words,
}: {
  shown: number;
  total: number;
  pageSize: number;
  hasMore: boolean;
  loading: boolean;
  failed: boolean;
  onMore: () => void;
  words: LoadMoreWords;
}) {
  const [announce, setAnnounce] = useState("");
  const before = useRef<number | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const done = useRef<HTMLParagraphElement>(null);

  // Once a page has landed: say how many rows came, and keep the focus on the strip.
  useEffect(() => {
    if (loading || before.current === null) return;
    const came = shown - before.current;
    const hadFocus = document.activeElement === document.body || document.activeElement === button.current;
    before.current = null;
    if (came > 0) setAnnounce(words.added(came));
    if (hadFocus && !hasMore) done.current?.focus();
  }, [loading, shown, hasMore, words]);

  if (total <= pageSize && !hasMore) return null;

  const left = Math.max(0, total - shown);
  const ratio = total > 0 ? Math.min(1, shown / total) : 1;
  const more = () => {
    before.current = shown;
    onMore();
  };

  return (
    <nav aria-label={words.label} className="mx-4 mt-8 lg:mx-0">
      <div className="h-0.5 w-full overflow-hidden rounded-full bg-border" aria-hidden>
        <div
          className="h-full rounded-full bg-foreground transition-[width] duration-500 ease-(--ease-out) motion-reduce:transition-none"
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <p className="text-sm text-muted-foreground">
          <span className="font-bold text-foreground tabular">{words.shown(shown, total)}</span>
          {hasMore && left > 0 && <span> · {words.left(left)}</span>}
        </p>
        {hasMore ? (
          failed && !loading ? (
            <div className="flex flex-wrap items-center gap-3">
              <p role="alert" className="inline-flex items-center gap-2 text-sm font-medium">
                <IconWarning className="size-4" aria-hidden /> {words.failed}
              </p>
              <Button ref={button} type="button" variant="outline" className="h-10" onClick={more}>
                {words.retry}
              </Button>
            </div>
          ) : (
            <Button
              ref={button}
              type="button"
              variant="outline"
              className="h-10 min-w-56"
              onClick={more}
              disabled={loading}
              aria-busy={loading || undefined}
            >
              {loading ? (
                <>
                  <IconCircleNotch className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
                  {words.loading}
                </>
              ) : (
                <>
                  <IconArrowDown className="size-4" aria-hidden />
                  {words.next(Math.min(pageSize, left || pageSize))}
                </>
              )}
            </Button>
          )
        ) : (
          <p ref={done} tabIndex={-1} className="inline-flex items-center gap-2 text-sm font-medium outline-none">
            <IconCheck className="size-4" aria-hidden />
            {words.all(total)}
          </p>
        )}
      </div>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
    </nav>
  );
}
