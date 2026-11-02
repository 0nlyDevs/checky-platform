"use client";

import type { Item, ItemPage, Me } from "@fanilo/shared";
import { useParams, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Dialog } from "radix-ui";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { useAssistant } from "@/components/assistant/assistant-context";
import { NAV, WORKSPACE_NAV } from "@/components/shell/nav";
import { toClaim } from "@/components/claims/verdict";
import { fetcher } from "@/lib/api";
import { palette as p } from "@/lib/i18n/fr/palette";
import { IconFolderOpen, IconMagnifyingGlass, IconMoon, IconQuestion, IconScan, IconSparkle, type Icon } from "@/lib/icons";
import { cn } from "@/lib/utils";

/** Anything can open the palette (the shell's search button included) with `openPalette()`. */
export const PALETTE_EVENT = "checky:palette";
export const SHORTCUTS_EVENT = "checky:shortcuts";
export function openPalette() {
  window.dispatchEvent(new Event(PALETTE_EVENT));
}

type Entry = { id: string; group: keyof typeof p.groups; icon: Icon; label: string; hint?: string; keys?: string[]; run: () => void };

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Ctrl/⌘+K and « / »: spaces, dossiers (searched on the server) and actions, from anywhere in the desk. */
export function CommandPalette() {
  const { ws } = useParams<{ ws?: string }>();
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const { setOpen: openAssistant } = useAssistant();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [cursor, setCursor] = useState(0);
  const listId = useId();
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const show = () => setOpen(true);
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
        return;
      }
      if (e.key !== "/" || document.querySelector('[role="dialog"], [role="alertdialog"]') || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const el = e.target as HTMLElement | null;
      if (el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable)) return;
      e.preventDefault();
      setOpen(true);
    };
    window.addEventListener(PALETTE_EVENT, show);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener(PALETTE_EVENT, show);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 180);
    return () => clearTimeout(id);
  }, [query]);

  const { data: me } = useSWR<Me>(open ? "/me" : null, fetcher);
  const key = open && ws ? `/workspaces/${ws}/items?limit=5${debounced ? `&q=${encodeURIComponent(debounced)}` : ""}` : null;
  const { data: found, isLoading, isValidating } = useSWR<ItemPage>(key, fetcher, { keepPreviousData: true });

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setDebounced("");
    setCursor(0);
  }, []);

  const entries = useMemo(() => {
    const list: Entry[] = [];
    const go = (path: string) => () => router.push(path as never);
    if (ws) {
      const role = me?.memberships.find((m) => m.workspace_id === ws)?.role;
      const restricted = role === "issuer" || role === "veilleur";
      const spaces = restricted ? NAV.filter((n) => n.path === (role === "issuer" ? "registre" : "veille")) : [...NAV, ...WORKSPACE_NAV];
      for (const n of spaces) list.push({ id: `space-${n.path}`, group: "spaces", icon: n.icon, label: n.label, run: go(`/w/${ws}/${n.path}`) });
      // a stale answer (for the previous letters) is not offered while the next one is on its way
      for (const item of query.trim() === debounced && !isValidating ? (found?.items ?? []) : []) {
        const claim = toClaim(item as Item);
        list.push({ id: `claim-${item.id}`, group: "claims", icon: IconFolderOpen, label: item.title, hint: claim.ref, run: go(`/w/${ws}/affirmations/${item.id}`) });
      }
      list.push({ id: "act-check", group: "actions", icon: IconScan, label: p.actions.check, keys: ["V"], run: go(`/w/${ws}/verifier`) });
    }
    list.push(
      { id: "act-ask", group: "actions", icon: IconSparkle, label: p.actions.ask, run: () => openAssistant(true) },
      { id: "act-theme", group: "actions", icon: IconMoon, label: p.actions.theme, run: () => setTheme(resolvedTheme === "dark" ? "light" : "dark") },
      { id: "act-keys", group: "actions", icon: IconQuestion, label: p.actions.shortcuts, keys: ["?"], run: () => window.dispatchEvent(new Event(SHORTCUTS_EVENT)) },
    );
    return list;
  }, [ws, me, found, query, debounced, isValidating, router, openAssistant, setTheme, resolvedTheme]);

  const shown = useMemo(() => {
    const q = fold(query.trim());
    if (!q) return entries;
    // Dossiers were already matched by the server; spaces and actions are matched here, accents ignored.
    return entries.filter((e) => e.group === "claims" || fold(`${e.label} ${p.groups[e.group]}`).includes(q));
  }, [entries, query]);

  const at = Math.min(cursor, Math.max(0, shown.length - 1));
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${at}"]`)?.scrollIntoView({ block: "nearest" });
  }, [at, shown.length]);

  function run(entry?: Entry) {
    if (!entry) return;
    close();
    entry.run();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (shown.length) setCursor((at + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      setCursor(e.key === "Home" ? 0 : Math.max(0, shown.length - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(shown[at]);
    }
  }

  const groups = (Object.keys(p.groups) as (keyof typeof p.groups)[]).filter((g) => shown.some((e) => e.group === g));

  return (
    <Dialog.Root open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-[14vh] left-1/2 z-50 grid max-h-[70vh] w-[min(620px,calc(100vw-2rem))] -translate-x-1/2 grid-rows-[auto_1fr] overflow-hidden rounded-[22px] border border-border bg-popover text-popover-foreground shadow-2xl outline-none max-sm:top-2 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
        >
          <Dialog.Title className="sr-only">{p.title}</Dialog.Title>
          <div className="flex items-center gap-3 border-b border-border px-4 py-3.5">
            <IconMagnifyingGlass className="size-5 shrink-0 text-muted-foreground" aria-hidden />
            <input
              role="combobox"
              aria-expanded
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={shown.length ? `${listId}-${at}` : undefined}
              aria-label={p.title}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setCursor(0);
              }}
              onKeyDown={onKeyDown}
              placeholder={p.placeholder}
              autoComplete="off"
              spellCheck={false}
              className="min-w-0 flex-1 bg-transparent py-1.5 text-[1.0625rem] outline-none placeholder:text-muted-foreground"
            />
            <kbd className="hidden rounded-md border border-border px-1.5 py-0.5 text-xs text-muted-foreground sm:block">Échap</kbd>
          </div>
          <div ref={listRef} id={listId} role="listbox" aria-label={p.list} className="overflow-y-auto p-2">
            {groups.map((g) => (
              <div key={g} role="group" aria-labelledby={`${listId}-g-${g}`}>
                <p id={`${listId}-g-${g}`} role="presentation" className="px-2.5 pt-2.5 pb-1 text-xs font-bold text-muted-foreground">
                  {p.groups[g]}
                </p>
                {shown.map((e, i) =>
                  e.group !== g ? null : (
                    <div
                      key={e.id}
                      id={`${listId}-${i}`}
                      data-index={i}
                      role="option"
                      aria-selected={i === at}
                      onMouseMove={() => i !== at && setCursor(i)}
                      onClick={() => run(e)}
                      className={cn("flex h-11 cursor-pointer items-center gap-3 rounded-xl px-2.5 text-sm text-popover-foreground", i === at && "bg-raised")}
                    >
                      <e.icon className="size-[1.125rem] shrink-0 text-muted-foreground" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{e.label}</span>
                      {e.hint && <span className="shrink-0 font-display text-xs font-bold text-muted-foreground tabular">{e.hint}</span>}
                      {e.keys?.map((k) => (
                        <kbd key={k} className="rounded-md border border-border px-1.5 py-0.5 text-xs text-muted-foreground">
                          {k}
                        </kbd>
                      ))}
                    </div>
                  ),
                )}
              </div>
            ))}
            {!shown.length && (
              <p role="status" className="px-2.5 py-4 text-sm text-muted-foreground">
                {isLoading || isValidating ? p.loading : p.empty}
              </p>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

