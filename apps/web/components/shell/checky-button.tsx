"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useAssistant } from "@/components/assistant/assistant-context";
import { IconSparkle, IconX } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";

const a = t.assistant;
const HINT_KEY = "checky:hint-seen";
const HINT_EVENT = "checky:hint";

// The first-visit hint is a tiny store over localStorage, read without an effect.
const hintStore = {
  subscribe(cb: () => void) {
    addEventListener(HINT_EVENT, cb);
    return () => removeEventListener(HINT_EVENT, cb);
  },
  seen() {
    try {
      return localStorage.getItem(HINT_KEY) === "1";
    } catch {
      return true;
    }
  },
  done() {
    try {
      localStorage.setItem(HINT_KEY, "1");
    } catch {
      // without storage the hint shows again next visit
    }
    dispatchEvent(new Event(HINT_EVENT));
  },
};

/**
 * Bottom-right corner: Checky alone, the screen's one floating action. Its label slides out to the
 * left on hover and focus; it opens the assistant as a panel growing out of this corner.
 */
export function CheckyButton({ scope }: { scope: "public" | "desk" }) {
  const { open, setOpen, launcher } = useAssistant();
  // Desk only: a hand-drawn arrow, once, until the first scroll or the first open.
  const seen = useSyncExternalStore(hintStore.subscribe, hintStore.seen, () => true);
  const hint = scope === "desk" && !seen;

  useEffect(() => {
    if (!hint) return;
    if (open) return hintStore.done();
    const onScroll = () => scrollY > 40 && hintStore.done();
    addEventListener("scroll", onScroll, { passive: true });
    return () => removeEventListener("scroll", onScroll);
  }, [hint, open]);

  return (
    <>
      <button
        ref={launcher}
        type="button"
        className="checky-fab"
        data-scope={scope}
        data-ripple
        aria-expanded={open}
        aria-controls="assistant-panel"
        aria-label={open ? a.close : a.ask}
        onClick={() => setOpen(!open)}
      >
        <span className="checky-fab-label" aria-hidden>
          <span>
            <b>{a.ask}</b>
          </span>
        </span>
        <span className="checky-fab-icon" aria-hidden>
          <IconSparkle className="checky-fab-open" />
          <IconX className="checky-fab-close" />
        </span>
      </button>
      {hint && (
        <div className="checky-hint" aria-hidden>
          <p>{a.hint}</p>
          <svg viewBox="0 0 110 96">
            <path pathLength={1} d="M4 70 C 22 72, 40 60, 44 42 C 48 22, 26 18, 24 34 C 22 52, 58 58, 76 66 C 92 74, 100 82, 106 92" />
            <path pathLength={1} d="M93 90 L107 93 L104 79" />
          </svg>
        </div>
      )}
    </>
  );
}
