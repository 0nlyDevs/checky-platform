"use client";

import { useAssistant } from "@/components/assistant/assistant-context";
import { IconSparkle, IconX } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";

const a = t.assistant;
/**
 * Bottom-right corner: Checky alone, the screen's one floating action. Its label slides out to the
 * left on hover and focus; it opens the assistant as a panel growing out of this corner.
 */
export function CheckyButton({ scope }: { scope: "public" | "desk" }) {
  const { open, setOpen, launcher } = useAssistant();

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
    </>
  );
}
