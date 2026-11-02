"use client";

import { useParams, useRouter } from "next/navigation";
import { Dialog } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import { SHORTCUTS_EVENT } from "@/components/shell/command-palette";
import { palette as p } from "@/lib/i18n/fr/palette";
import { IconX } from "@/lib/icons";

/** G then a letter: where it goes, relative to /w/[ws]. */
const GO: Record<string, string> = { d: "affirmations", s: "sources", e: "membres", p: "parametres" };
const G_WINDOW_MS = 1200;

const typing = (el: EventTarget | null) => {
  const node = el as HTMLElement | null;
  return Boolean(node && (/^(INPUT|TEXTAREA|SELECT)$/.test(node.tagName) || node.isContentEditable));
};

/** Single-key shortcuts of the desk (V, G then D/S/E/P, ?) and their help dialog. Ignored while typing or in a dialog. */
export function Shortcuts() {
  const { ws } = useParams<{ ws?: string }>();
  const router = useRouter();
  const [help, setHelp] = useState(false);
  const pendingG = useRef(0);

  useEffect(() => {
    const show = () => setHelp(true);
    window.addEventListener(SHORTCUTS_EVENT, show);
    return () => window.removeEventListener(SHORTCUTS_EVENT, show);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
      // A dialog (palette, sheet, confirmation) owns the keyboard while it is open.
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
      const key = e.key.toLowerCase();
      if (pendingG.current && Date.now() - pendingG.current < G_WINDOW_MS) {
        pendingG.current = 0;
        if (ws && GO[key]) {
          e.preventDefault();
          router.push(`/w/${ws}/${GO[key]}` as never);
        }
        return;
      }
      if (e.key === "?") {
        e.preventDefault();
        setHelp(true);
      } else if (key === "g") {
        pendingG.current = Date.now();
      } else if (key === "v" && ws) {
        e.preventDefault();
        router.push(`/w/${ws}/verifier`);
        // the field exists once the page has rendered
        let tries = 0;
        const focus = setInterval(() => {
          const field = document.getElementById("verify-input");
          if (field || ++tries > 20) {
            clearInterval(focus);
            field?.focus();
          }
        }, 60);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ws, router]);

  return (
    <Dialog.Root open={help} onOpenChange={setHelp}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content className="fixed top-[18vh] left-1/2 z-50 w-[min(460px,calc(100vw-2rem))] -translate-x-1/2 rounded-[22px] border border-border bg-popover p-5 text-popover-foreground shadow-2xl outline-none max-sm:top-4 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0">
          <Dialog.Title className="font-display text-lg font-bold">{p.help.title}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">{p.help.description}</Dialog.Description>
          <dl className="mt-4 grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2.5 text-sm">
            {p.help.rows.map((r) => (
              <div key={r.label} className="contents">
                <dt>{r.label}</dt>
                <dd className="flex gap-1">
                  {r.keys.map((k, i) => (
                    <span key={k} className="flex items-center gap-1">
                      {i > 0 && <span className="text-muted-foreground" aria-hidden>puis</span>}
                      <kbd className="rounded-md border border-border px-1.5 py-0.5 text-xs">{k}</kbd>
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
          <Dialog.Close className="absolute top-3 right-3 grid size-11 place-items-center rounded-full outline-none hover:bg-raised focus-visible:ring-2 focus-visible:ring-ring sm:size-9" aria-label={p.help.close}>
            <IconX className="size-4" aria-hidden />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
