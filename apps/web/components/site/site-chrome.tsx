"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { Wordmark } from "@/components/brand/logo";
import { OfflineBanner } from "@/components/pwa/offline-banner";
import { ThemeFace, useThemeFlip } from "@/components/shell/preference-dock";
import { brand } from "@/lib/brand";
import { LANGS, setLang, useDocumentLang, useLang, useT, type Messages } from "@/lib/i18n";
import { IconArrowRight, IconMagnifyingGlass, IconPaperPlaneTilt, IconQrCode, IconSealCheck, type Icon } from "@/lib/icons";
import { FONT_STEPS, setFontStep, useFontStep } from "@/lib/prefs";
import { useSlidingPill } from "@/lib/use-sliding-pill";
import { cn } from "@/lib/utils";

type Place = { href: string; label: string; icon: Icon; match: (p: string) => boolean };

/** The visitor's four places: check, report, the official feed, the seal scanner. */
const places = (t: Messages): Place[] => [
  { href: "/verifies", label: t.site.pub.nav.check, icon: IconMagnifyingGlass, match: (p) => p.startsWith("/verifies") || p.startsWith("/v/") },
  { href: "/signaler", label: t.site.pub.nav.report, icon: IconPaperPlaneTilt, match: (p) => p.startsWith("/signaler") || p.startsWith("/suivi") },
  { href: "/officiel", label: t.registre.feed.title, icon: IconSealCheck, match: (p) => p.startsWith("/officiel") },
  { href: "/scanner", label: t.offline.scanner.title, icon: IconQrCode, match: (p) => p.startsWith("/scanner") || p.startsWith("/sceau") },
];

/** FR · MG · EN: the visitor's language, remembered on this device. The ink pill slides to the choice. */
export function LanguageSwitch({ className }: { className?: string }) {
  const lang = useLang();
  const l = useT().publicLayer.lang;
  useDocumentLang();
  const { host, pill, handlers } = useSlidingPill<HTMLDivElement>(lang);
  return (
    <div ref={host} role="group" aria-label={l.label} className={cn("seg", className)} {...handlers}>
      <span ref={pill} className="seg-pill" aria-hidden />
      {LANGS.map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          title={l.names[code]}
          aria-label={l.names[code]}
          aria-pressed={lang === code}
          data-pill-item
          data-current={lang === code || undefined}
          onClick={() => setLang(code)}
          className="seg-item"
        >
          {l.short[code]}
        </button>
      ))}
    </div>
  );
}

/** The public bar: the name, the four places on the ink island, the visitor's tools, the newsroom door. */
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
  return (
    <header className="site-bar print:hidden">
      <div className="site-bar-in">
        <Link href="/" className="site-word outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Wordmark />
        </Link>
        <SiteNav pathname={pathname} />
        <div className="site-tools">
          <LanguageSwitch className="site-hide-sm" />
          <FontButtons />
          <ThemeButton />
          <Link
            href="/connexion"
            className="group inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-sm font-bold text-primary-foreground outline-none hover:bg-primary-hover hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background site-hide-sm"
          >
            {s.nav.newsroom}
            <IconArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden />
          </Link>
        </div>
      </div>
      <OfflineBanner scope="site" />
    </header>
  );
}

/** The ink island of the desk, with the same paper pill: it rests on the current place and follows
 *  the pointer and the keyboard over the others (lib/use-sliding-pill.ts). */
function SiteNav({ pathname }: { pathname: string }) {
  const t = useT();
  const list = places(t);
  const active = list.findIndex((p) => p.match(pathname));
  const { host, pill, handlers } = useSlidingPill<HTMLUListElement>(active);
  return (
    <nav aria-label={t.site.nav.label} className="site-nav">
      <div className="tab-island">
        <span ref={pill} className="tab-pill" aria-hidden />
        <ul ref={host} className="tab-list" {...handlers}>
          {list.map(({ href, label, icon: Glyph }, i) => (
            <li key={href}>
              <Link href={href} className="tab" data-ripple data-pill-item data-current={i === active || undefined} aria-current={i === active ? "page" : undefined}>
                <Glyph className="tab-icon" aria-hidden />
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

/** A− A+: the text size, remembered on this device (lib/prefs.ts). */
function FontButtons() {
  const f = useT().reach.font;
  const step = useFontStep();
  return (
    <div role="group" aria-label={f.label} className="site-round-group site-lg">
      <button type="button" className="site-round" disabled={step === 0} onClick={() => setFontStep(step - 1)} aria-label={f.smaller} title={f.smaller}>
        A−
      </button>
      <button
        type="button"
        className="site-round"
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

/** Light or dark for a visitor, with the same diagonal reveal as the desk. */
function ThemeButton() {
  const flip = useThemeFlip();
  return (
    <button type="button" onClick={flip} className="site-round" data-ripple>
      <ThemeFace flag={false} />
    </button>
  );
}

export function SiteFooter() {
  const t = useT();
  const s = t.site;
  const c = s.footer.cols;
  const link = "site-foot-link outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <footer className="site-foot print:hidden">
      <div className="site-foot-grid">
        <div>
          <Wordmark />
          <p className="mt-4 max-w-[44ch] text-pretty text-muted-foreground">{s.footer.what}</p>
          <p className="mt-3 max-w-[44ch] text-sm text-pretty text-muted-foreground">{s.footer.made}</p>
        </div>
        <nav aria-labelledby="foot-public">
          <h2 id="foot-public">{c.public}</h2>
          <ul>
            {places(t).map((p) => (
              <li key={p.href}>
                <Link href={p.href} className={link}>
                  {p.label}
                </Link>
              </li>
            ))}
            <li>
              <a href="/flashs" className={link}>
                {t.publicLayer.footer.flashs}
              </a>
            </li>
          </ul>
        </nav>
        <nav aria-labelledby="foot-newsrooms">
          <h2 id="foot-newsrooms">{c.newsrooms}</h2>
          <ul>
            <li>
              <Link href="/connexion" className={link}>
                {s.nav.signIn}
              </Link>
            </li>
            <li>
              <Link href="/inscription" className={cn(link, "font-bold")}>
                {s.home.newsroomsCta}
              </Link>
            </li>
          </ul>
        </nav>
      </div>
      <div className="site-ghost" aria-hidden>
        <span>{brand.name.toUpperCase()}</span>
      </div>
      <div className="site-legal">
        <span>{s.footer.fictional}</span>
        <span>{brand.name} · Antananarivo</span>
      </div>
    </footer>
  );
}
