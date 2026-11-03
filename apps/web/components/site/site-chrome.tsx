"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { Wordmark } from "@/components/brand/logo";
import { FontSizeControl } from "@/components/prefs/prefs-controls";
import { OfflineBanner } from "@/components/pwa/offline-banner";
import { ThemeFace, useThemeFlip } from "@/components/shell/preference-dock";
import { brand } from "@/lib/brand";
import { LANGS, setLang, useDocumentLang, useLang, useT, type Messages } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const links = (s: Messages["site"], scan: string) =>
  [
    { href: "/", label: s.pub.nav.check, match: (p: string) => p === "/" || p === "/accueil" },
    { href: "/verifies", label: s.pub.nav.verified, match: (p: string) => p.startsWith("/verifies") || p.startsWith("/v/") },
    { href: "/signaler", label: s.pub.nav.report, match: (p: string) => p.startsWith("/signaler") || p.startsWith("/suivi") },
    { href: "/scanner", label: scan, match: (p: string) => p.startsWith("/scanner") || p.startsWith("/sceau") },
  ] as const;

/** FR · MG · EN: the visitor's language, remembered on this device. French fills any gap. */
export function LanguageSwitch({ className }: { className?: string }) {
  const lang = useLang();
  const l = useT().publicLayer.lang;
  useDocumentLang();
  return (
    <div role="group" aria-label={l.label} className={cn("flex rounded-md border border-border bg-card p-0.5", className)}>
      {LANGS.map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          title={l.names[code]}
          aria-label={l.names[code]}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
          className={cn(
            "h-8 min-w-9 rounded-sm px-2 font-display text-xs font-bold tracking-wide outline-none focus-visible:ring-2 focus-visible:ring-ring",
            lang === code ? "bg-foreground text-background" : "text-foreground hover:bg-accent",
          )}
        >
          {l.short[code]}
        </button>
      ))}
    </div>
  );
}

/** The public top bar: the name, three places a visitor goes, the assistant and the newsroom door. */
export function SiteHeader() {
  // On a dynamic route the path is only known at request time: the shell shows the bar unlit until then.
  return (
    <Suspense fallback={<Bar pathname="" />}>
      <LitBar />
    </Suspense>
  );
}

function LitBar() {
  return <Bar pathname={usePathname()} />;
}

function Bar({ pathname }: { pathname: string }) {
  const t = useT();
  const s = t.site;
  const LINKS = links(s, t.offline.scanner.title);
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background print:hidden">
      <div className="mx-auto flex max-w-[88rem] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:gap-x-6 lg:px-10">
        <Link href="/" className="shrink-0 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Wordmark />
        </Link>
        <nav aria-label={s.nav.label} className="hidden md:block">
          <ul className="flex gap-1">
            {LINKS.map((l) => {
              const active = l.match(pathname);
              return (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "rounded-md px-3 py-2 underline-offset-[7px] outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active ? "font-bold underline decoration-2" : "hover:bg-accent",
                    )}
                  >
                    {l.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <LanguageSwitch />
          <FontSizeControl />
          <ThemeButton />
          <Link href="/connexion" className="hidden h-10 items-center rounded-md bg-primary px-3.5 text-sm font-bold text-primary-foreground outline-none hover:bg-primary-hover hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex">
            {s.nav.newsroom}
          </Link>
        </div>
      </div>
      {/* On a phone the three places stay one tap away, under the bar. */}
      <nav aria-label={s.nav.label} className="border-t border-border md:hidden">
        <ul className="grid grid-cols-4">
          {LINKS.map((l) => {
            const active = l.match(pathname);
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "block border-b-2 px-2 py-2.5 text-center text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "border-foreground font-bold" : "border-transparent",
                  )}
                >
                  {l.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <OfflineBanner scope="site" />
    </header>
  );
}

/** Light or dark for a visitor, with the same diagonal reveal as the desk (Checky is in the corner). */
function ThemeButton() {
  const flip = useThemeFlip();
  return (
    <button type="button" onClick={flip} className="site-theme" data-ripple>
      <ThemeFace flag={false} />
    </button>
  );
}

export function SiteFooter() {
  const t = useT();
  const s = t.site;
  const LINKS = links(s, t.offline.scanner.title);
  return (
    <footer className="border-t border-border print:hidden">
      <div className="mx-auto grid max-w-[88rem] gap-8 px-4 pt-10 pb-28 md:grid-cols-[minmax(0,1.4fr)_repeat(2,minmax(0,1fr))] lg:px-10">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-[46ch] text-pretty text-muted-foreground">{s.footer.what}</p>
          <p className="mt-3 max-w-[46ch] text-sm text-pretty text-muted-foreground">{s.footer.made}</p>
        </div>
        <nav aria-label={s.nav.label}>
          <ul className="space-y-2">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="underline-offset-4 hover:underline">
                  {l.label}
                </Link>
              </li>
            ))}
            <li>
              <a href="/flashs" className="underline-offset-4 hover:underline">
                {t.publicLayer.footer.flashs}
              </a>
            </li>
          </ul>
        </nav>
        <div className="space-y-2">
          <p>
            <Link href="/inscription" className="font-bold underline underline-offset-4">
              {s.home.newsroomsCta}
            </Link>
          </p>
          <p>
            <Link href="/connexion" className="underline-offset-4 hover:underline">
              {s.nav.signIn}
            </Link>
          </p>
          <p className="pt-2 text-sm text-muted-foreground">{s.footer.fictional}</p>
        </div>
      </div>
      <p className="sr-only">{brand.name}</p>
    </footer>
  );
}
