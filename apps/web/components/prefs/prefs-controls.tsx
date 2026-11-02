"use client";

import { useTheme } from "next-themes";
import { toast } from "sonner";
import { DropdownMenuCheckboxItem, DropdownMenuItem, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { useT } from "@/lib/i18n";
import { IconLeaf, IconMinus, IconPlus } from "@/lib/icons";
import { DEFAULT_FONT, FONT_STEPS, setEco, setFontStep, useEco, useFontStep } from "@/lib/prefs";
import { cn } from "@/lib/utils";

/** Turn Mode éco on or off, and on a light screen suggest the dark theme (it saves an OLED's battery). */
function useEcoToggle() {
  const r = useT().reach.eco;
  const { resolvedTheme, setTheme } = useTheme();
  return (on: boolean) => {
    setEco(on);
    if (!on) {
      toast(r.off);
      return;
    }
    if (resolvedTheme === "light") {
      toast(r.on, { description: r.darkTip, action: { label: r.darkAction, onClick: () => setTheme("dark") } });
    } else {
      toast(r.on, { description: r.hint });
    }
  };
}

/** Mode éco as a checkbox row of a dropdown menu (the desk's user menu). */
export function EcoMenuItem() {
  const r = useT().reach.eco;
  const eco = useEco();
  const toggle = useEcoToggle();
  return (
    <DropdownMenuCheckboxItem checked={eco} onCheckedChange={(v) => toggle(v === true)} onSelect={(e) => e.preventDefault()}>
      <IconLeaf className="size-4" aria-hidden />
      <span className="flex-1">{r.label}</span>
    </DropdownMenuCheckboxItem>
  );
}

/** A− 100 % A+ as a row of a dropdown menu: the menu stays open while the text grows or shrinks. */
export function FontMenuRow() {
  const f = useT().reach.font;
  const step = useFontStep();
  return (
    <>
      <DropdownMenuLabel>{f.label}</DropdownMenuLabel>
      <div className="flex items-center gap-1 px-1 pb-1">
        <DropdownMenuItem
          className="justify-center"
          disabled={step === 0}
          aria-label={f.smaller}
          onSelect={(e) => {
            e.preventDefault();
            setFontStep(step - 1);
          }}
        >
          <IconMinus className="size-4" aria-hidden /> A
        </DropdownMenuItem>
        <DropdownMenuItem
          className="flex-1 justify-center tabular"
          aria-label={`${f.reset} (${f.value(FONT_STEPS[step])})`}
          onSelect={(e) => {
            e.preventDefault();
            setFontStep(DEFAULT_FONT);
          }}
        >
          {f.value(FONT_STEPS[step])}
        </DropdownMenuItem>
        <DropdownMenuItem
          className="justify-center"
          disabled={step === FONT_STEPS.length - 1}
          aria-label={f.larger}
          onSelect={(e) => {
            e.preventDefault();
            setFontStep(step + 1);
          }}
        >
          <IconPlus className="size-4" aria-hidden /> A
        </DropdownMenuItem>
      </div>
    </>
  );
}

/** A− / A+ as two small buttons, for the public header. */
export function FontSizeControl({ className }: { className?: string }) {
  const f = useT().reach.font;
  const step = useFontStep();
  const btn =
    "inline-flex h-8 min-w-8 items-center justify-center rounded-sm px-1.5 font-display text-xs font-bold text-foreground outline-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:text-muted-foreground disabled:hover:bg-transparent";
  return (
    <div role="group" aria-label={f.label} className={cn("flex rounded-md border border-border bg-card p-0.5", className)}>
      <button type="button" className={btn} disabled={step === 0} onClick={() => setFontStep(step - 1)} aria-label={f.smaller} title={f.smaller}>
        A−
      </button>
      <button
        type="button"
        className={btn}
        disabled={step === FONT_STEPS.length - 1}
        onClick={() => setFontStep(step + 1)}
        aria-label={f.larger}
        title={`${f.larger} (${f.value(FONT_STEPS[step])})`}
      >
        A+
      </button>
    </div>
  );
}
