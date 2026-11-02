"use client";

import { createContext, Suspense, useContext, useMemo, useState } from "react";
import { IconChatCircle } from "@/lib/icons";
import { AssistantWidget } from "@/components/assistant/assistant-widget";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

type AssistantState = { open: boolean; setOpen: (open: boolean) => void };
const Ctx = createContext<AssistantState | null>(null);

/**
 * The site agent's place on the page. On a computer it is docked on the right and the page makes
 * room for it (it never covers what is being read); on a phone it is a sheet over the lower part.
 * Every launcher (rail, phone bar, public header) opens the same panel.
 */
export function AssistantProvider({ scope, children }: { scope: "public" | "desk"; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const value = useMemo(() => ({ open, setOpen }), [open]);
  return (
    <Ctx.Provider value={value}>
      <div data-assistant={open ? "open" : "closed"} className={cn("min-h-dvh transition-[padding] duration-300 ease-out-expo", open && "lg:pr-[25rem]")}>
        {children}
      </div>
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

/** A button that opens (or closes) the assistant; its look follows where it sits. */
export function AssistantLauncher({ variant, className }: { variant: "rail" | "bar" | "header"; className?: string }) {
  const { open, setOpen } = useAssistant();
  const a = t.assistant;
  if (variant === "bar") {
    return (
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={cn(
          "flex w-full flex-col items-center gap-1 px-1 pt-2 pb-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
          open ? "font-bold text-sidebar-foreground" : "text-sidebar-foreground",
          className,
        )}
      >
        <span className={cn("grid h-6 w-12 place-items-center rounded-full", open && "bg-sidebar-primary text-sidebar-primary-foreground")}>
          <IconChatCircle className="size-[1.125rem]" aria-hidden />
        </span>
        {a.short}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={() => setOpen(!open)}
      aria-expanded={open}
      className={cn(
        "flex items-center gap-2.5 rounded-md text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        variant === "rail" ? "w-full bg-live px-3 py-2.5 text-live-foreground hover:bg-live/90" : "h-10 border border-border bg-card px-3 text-sm font-bold hover:border-foreground",
        className,
      )}
    >
      <IconChatCircle className={cn("shrink-0", variant === "rail" ? "size-5 text-action" : "size-4")} aria-hidden />
      {variant === "rail" ? (
        <span className="min-w-0">
          <span className="block text-sm font-bold">{a.title}</span>
          <span className="block truncate text-xs text-live-muted">{open ? a.close : a.launcherHint}</span>
        </span>
      ) : (
        <span>{a.short}</span>
      )}
    </button>
  );
}
