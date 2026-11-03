"use client";

import Link from "next/link";
import { useTheme } from "next-themes";
import { IconGear, IconMoon, IconSun } from "@/lib/icons";
import { LANGS, setLang, t, useLang } from "@/lib/i18n";
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
 * Bottom-left: the preferences, one floating object (theme, language, then settings). Each label
 * flags out to the right on hover and focus. The language button steps FR → MG → EN; the avatar
 * menu offers the three at once (and is the only place on a phone).
 */
export function PreferenceDock({ settingsHref }: { settingsHref?: string }) {
  const flip = useThemeFlip();
  const lang = useLang();
  const l = t.publicLayer.lang;
  const next = LANGS[(LANGS.indexOf(lang) + 1) % LANGS.length];
  return (
    <div className="dock" role="toolbar" aria-label={t.nav.preferences} aria-orientation="vertical">
      <button type="button" className="dock-btn" data-ripple onClick={flip}>
        <ThemeFace />
      </button>
      <button type="button" className="dock-btn" data-ripple onClick={() => setLang(next)} aria-label={`${t.reach.lang.current(l.names[lang])} → ${l.names[next]}`}>
        <span className="dock-icon grid place-items-center font-display text-sm font-bold" aria-hidden>
          {l.short[lang]}
        </span>
        <span className="dock-flag" aria-hidden>
          {t.reach.lang.current(l.names[lang])}
        </span>
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
