"use client";

import { createContext, Suspense, useContext, useMemo, useRef, useState, type RefObject } from "react";
import { AssistantWidget } from "@/components/assistant/assistant-widget";
import { CheckyButton } from "@/components/shell/checky-button";

type AssistantState = {
  open: boolean;
  setOpen: (open: boolean) => void;
  /** The corner button: focus goes back to it when the panel closes. */
  launcher: RefObject<HTMLButtonElement | null>;
};
const Ctx = createContext<AssistantState | null>(null);

/**
 * The site agent's place on the page: the Checky button in the bottom-right corner, and the panel
 * that grows out of it. The same corner on the desk, the public site and the sign-in pages.
 */
export function AssistantProvider({ scope, children }: { scope: "public" | "desk"; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const value = useMemo(() => ({ open, setOpen, launcher }), [open]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <CheckyButton scope={scope} />
      {/* It reads the route (page, workspace): on dynamic routes that waits for the request. */}
      <Suspense fallback={null}>
        <AssistantWidget scope={scope} />
      </Suspense>
    </Ctx.Provider>
  );
}

export function useAssistant(): AssistantState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAssistant needs an AssistantProvider");
  return ctx;
}
