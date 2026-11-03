"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Wordmark } from "@/components/brand/logo";
import { Em, Lines, useStill } from "@/components/site/public/kit";
import { LanguageSwitch, ThemeButton } from "@/components/site/site-chrome";
import { useT } from "@/lib/i18n";
import { IconArrowLeft, IconCheck } from "@/lib/icons";
import { useSlidingPill } from "@/lib/use-sliding-pill";

/**
 * The doors into the desk, sign-in and sign-up: a full-height clip of a newsroom on the left (the
 * landing's world, ink in both themes), the form on the right under a switch whose ink pill slides
 * between the two doors. The parts that read the address wait in Suspense (cacheComponents).
 */
export function AuthDoors({ children }: { children: React.ReactNode }) {
  const t = useT();
  const a = t.look.auth;
  return (
    <div className="auth-doors">
      <Suspense fallback={<Side up={false} />}>
        <LitSide />
      </Suspense>
      <section className="auth-panel">
        <div className="auth-top">
          <Link
            href="/verifies"
            className="group inline-flex h-10 items-center gap-2 rounded-full px-1 text-sm font-bold text-foreground outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
          >
            <IconArrowLeft className="size-4 transition-transform duration-300 group-hover:-translate-x-0.5" aria-hidden />
            {a.back}
          </Link>
          <div className="flex items-center gap-1.5">
            <LanguageSwitch />
            <ThemeButton />
          </div>
        </div>
        <div className="auth-box">
          <Suspense fallback={<Doors path="" suite={null} />}>
            <LitDoors />
          </Suspense>
          {children}
        </div>
        <p className="auth-made">{t.site.footer.made}</p>
      </section>
    </div>
  );
}

function LitSide() {
  return <Side up={usePathname().startsWith("/inscription")} />;
}

/** The clip and the promise: the radio studio to sign in, a newsroom on air to sign up. */
function Side({ up }: { up: boolean }) {
  const t = useT();
  const a = t.look.auth;
  const still = useStill();
  return (
    <aside className="auth-side" aria-label={t.site.auth.title}>
      {!still && (
        <video
          key={up ? "up" : "in"}
          className="auth-video"
          src={up ? "/site/landing/videos/tv-reportage.mp4" : "/site/landing/videos/studio-radio.mp4"}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          aria-hidden
        />
      )}
      <div className="auth-shade" aria-hidden />
      <Link href="/" className="auth-word outline-none focus-visible:ring-2 focus-visible:ring-[#f3f2ee]">
        <Wordmark />
      </Link>
      <div className="auth-promise">
        <Lines as="h2" className="pub-display auth-title" lines={(up ? a.heroUp : a.hero).map((line, i) => <Em key={i} text={line} />)} />
        {up ? (
          <ul className="rise auth-points" style={{ "--d": "0.3s" } as React.CSSProperties}>
            {t.site.home.newsroomsPoints.map((point) => (
              <li key={point}>
                <IconCheck className="size-5 shrink-0" aria-hidden />
                {point}
              </li>
            ))}
          </ul>
        ) : (
          <p className="rise auth-lead" style={{ "--d": "0.3s" } as React.CSSProperties}>
            {t.site.auth.lead}
          </p>
        )}
        <a href="/site/landing/videos/CREDITS.md" target="_blank" rel="noreferrer" className="auth-credits">
          {a.credits}
        </a>
      </div>
    </aside>
  );
}

function LitDoors() {
  return <Doors path={usePathname()} suite={useSearchParams().get("suite")} />;
}

/** Se connecter · Créer un compte, the ink pill under the open door; `?suite=` follows across. */
function Doors({ path, suite }: { path: string; suite: string | null }) {
  const t = useT();
  const up = path.startsWith("/inscription");
  const current = path ? (up ? 1 : 0) : -1;
  const { host, pill, handlers } = useSlidingPill<HTMLElement>(current);
  const q = suite ? `?suite=${encodeURIComponent(suite)}` : "";
  const doors = [
    { href: `/connexion${q}`, label: t.auth.signIn },
    { href: `/inscription${q}`, label: t.auth.toSignUpLink },
  ];
  return (
    <nav ref={host} aria-label={t.look.auth.doors} className="seg seg-lg seg-fill" {...handlers}>
      <span ref={pill} className="seg-pill" aria-hidden />
      {doors.map((d, i) => (
        <Link key={d.href} href={d.href} className="seg-item" data-pill-item data-current={i === current || undefined} aria-current={i === current ? "page" : undefined}>
          {d.label}
        </Link>
      ))}
    </nav>
  );
}
