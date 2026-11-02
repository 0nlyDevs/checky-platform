"use client";

import Link from "next/link";
import { useTheme } from "next-themes";
import { IconGear, IconMoon, IconSun } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";
import { toggleThemeWithReveal } from "@/lib/theme-reveal";

/** Flip light/dark from whatever the page shows now (the class next-themes writes). */
export function useThemeFlip() {
  const { setTheme } = useTheme();
  return () => toggleThemeWithReveal(document.documentElement.classList.contains("dark") ? "light" : "dark", setTheme);
}

/**
 * The theme button's face follows the page's class through CSS, so the server and the first paint
 * agree: a moon and « Thème sombre » in light, a sun and « Thème clair » in dark.
 */
export function ThemeFace({ flag = true }: { flag?: boolean }) {
  return (
    <>
      <IconMoon className="dock-icon dark:hidden" aria-hidden />
      <IconSun className="dock-icon hidden dark:block" aria-hidden />
      <span className={flag ? "dock-flag dark:hidden" : "sr-only dark:hidden"}>{t.nav.toDark}</span>
      <span className={flag ? "dock-flag hidden dark:block" : "sr-only hidden dark:block"}>{t.nav.toLight}</span>
    </>
  );
}

/**
 * Bottom-left: the preferences, one floating object (theme, then settings). Each label flags out
 * to the right on hover and focus. The language button joins when the mg/en translations run.
 */
export function PreferenceDock({ settingsHref }: { settingsHref?: string }) {
  const flip = useThemeFlip();
  return (
    <div className="dock" role="toolbar" aria-label={t.nav.preferences} aria-orientation="vertical">
      <button type="button" className="dock-btn" data-ripple onClick={flip}>
        <ThemeFace />
      </button>
      {settingsHref && (
        <>
          <span className="dock-sep" aria-hidden />
          <Link href={settingsHref as never} className="dock-btn dock-opt" data-ripple>
            <IconGear className="dock-icon" aria-hidden />
            <span className="dock-flag">{t.nav.settings}</span>
          </Link>
        </>
      )}
    </div>
  );
}
