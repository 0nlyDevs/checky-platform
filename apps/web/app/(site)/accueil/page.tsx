import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { CreateDialog } from "@/components/site/create-dialog";
import { Exhibits } from "@/components/site/dossier/exhibits";
import { DossierMotion } from "@/components/site/dossier/motion";
import { Sequence } from "@/components/site/dossier/sequence";
import { DossierFooter } from "@/components/site/public/dossier-footer";
import { SiteHeader } from "@/components/site/public/site-header";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = {
  title: { absolute: `${brand.name} · ${t.site.metaTitle}` },
  description: t.site.metaDescription,
};

const s = t.site;
const a = s.affaire;
const WAVE = Array.from({ length: 40 }, (_, i) => 18 + 82 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.6)));
const TITLE = s.hero.title.split(" ");

/** The landing is a case file: the night of one rumour, its pieces, the report that clears, what leaves at 7. */
export default function LandingPage() {
  return (
    <>
      <a
        href="#contenu"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:bg-ink focus:px-3 focus:py-2 focus:text-manila"
      >
        {t.nav.skip}
      </a>
      <DossierMotion />

      <SiteHeader status={s.status.open} anchors />

      <main id="contenu">
        <section className="dossier-seq frame-x" aria-labelledby="hero-title">
          <Sequence>
            <div>
              <h1 id="hero-title" className="dossier-h1 disp" aria-label={s.hero.title}>
                {TITLE.map((w, i) => (
                  <span key={i} aria-hidden>
                    <span className="w">
                      <span style={{ animationDelay: `${i * 0.08}s` }}>{w}</span>
                    </span>
                    {i < TITLE.length - 1 ? " " : ""}
                  </span>
                ))}
              </h1>
              <div className="dossier-lead">
                <p>{s.hero.lead(brand.name)}</p>
                <Link href="#ouvrir" className="tab-btn">
                  {s.hero.start} <span className="arr" aria-hidden>→</span>
                </Link>
                <a href="#affaire" className="ulink text-lg">
                  {s.hero.see}
                </a>
              </div>
            </div>
          </Sequence>
        </section>

        {/* The night in four pieces, each with the desk's note in red. */}
        <section id="affaire" className="dossier-part frame-x bg-manila-deep" aria-labelledby="affaire-title">
          <div className="dossier-divider">
            <span className="divider-tab">{a.tab}</span>
            <h2 id="affaire-title" className="disp">
              {a.title}
            </h2>
          </div>
          <div className="dossier-board">
            <figure className="dossier-piece p1" data-observe>
              <span className="no">{a.piece(1)}</span>
              <div className="dossier-wa">
                <p className="fwd">{a.wa.forwarded}</p>
                <Image src="/site/dossier/piece-1.jpg" alt={s.hero.frames[0].alt} width={900} height={600} sizes="(min-width: 900px) 30vw, 90vw" />
                <p>{a.wa.text}</p>
              </div>
              <figcaption>{a.wa.meta}</figcaption>
              <p className="note">{a.wa.note}</p>
            </figure>
            <figure className="dossier-piece p2" data-observe style={{ transitionDelay: ".12s" }}>
              <span className="no">{a.piece(2)}</span>
              <div className="dossier-fb">
                <p className="who">{a.fb.page}</p>
                <p>{a.fb.text}</p>
                <p className="ct">{a.fb.count}</p>
              </div>
              <figcaption>{a.fb.meta}</figcaption>
              <p className="note">{a.fb.note}</p>
            </figure>
            <figure className="dossier-piece p3" data-observe style={{ transitionDelay: ".24s" }}>
              <span className="no">{a.piece(3)}</span>
              <div className="dossier-wa">
                <div className="dossier-wave" aria-hidden>
                  {WAVE.map((h, i) => (
                    <i key={i} style={{ height: `${h}%` }} />
                  ))}
                </div>
                <p>
                  <b className="tabular text-[#0f3b36]">{a.voice.time}</b> {a.voice.text}
                </p>
              </div>
              <figcaption>{a.voice.meta}</figcaption>
              <p className="note">{a.voice.note}</p>
            </figure>
            <div className="summary rise" data-observe>
              <h3>{a.summaryTitle}</h3>
              <p>{a.summary}</p>
            </div>
            <figure className="dossier-piece p4" data-observe style={{ transitionDelay: ".12s" }}>
              <span className="no">{a.piece(4)}</span>
              <div className="dossier-radio">{a.radio.text}</div>
              <figcaption>{a.radio.meta}</figcaption>
            </figure>
          </div>
        </section>

        {/* The method: a redacted report; reading it lifts the black. */}
        <section id="methode" className="dossier-part frame-x" aria-labelledby="methode-title">
          <div className="dossier-divider">
            <span className="divider-tab">{s.method.tab}</span>
            <h2 id="methode-title" className="disp">
              {s.method.title}
            </h2>
          </div>
          <article className="dossier-report">
            {s.method.steps.map((step) => (
              <div key={step.time} className="dossier-step" data-observe>
                <time className="tabular">{step.time}</time>
                <div>
                  <h3>{step.title}</h3>
                  <p>
                    {step.text.map((part, i) =>
                      i % 2 ? (
                        <span key={i} className="dossier-bar">
                          {part}
                        </span>
                      ) : (
                        part
                      ),
                    )}
                  </p>
                </div>
              </div>
            ))}
            <div className="sig">
              <span>
                {s.method.report}
                <br />
                {s.method.signature}
              </span>
              <span className="stamp" data-observe data-label={s.method.stamp} role="img" aria-label={s.method.stamp} />
            </div>
          </article>
        </section>

        {/* What leaves at 7, as the product makes it. */}
        <section id="sorties" className="dossier-part dossier-out frame-x" aria-labelledby="sorties-title">
          <div className="dossier-divider">
            <span className="divider-tab">{s.exhibits.tab}</span>
            <h2 id="sorties-title" className="disp">
              {s.exhibits.title}
            </h2>
          </div>
          <Exhibits />
        </section>

        {/* The one action: an opening card. */}
        <section id="ouvrir" className="dossier-part frame-x" aria-labelledby="ouvrir-title">
          <div className="dossier-open">
            <div>
              <h2 id="ouvrir-title" className="disp">
                {s.close.title}
              </h2>
              <p className="sub">{s.close.text}</p>
              <p className="mt-6 text-lg">
                <Link href="/verifies" className="ulink">
                  {s.pub.check.title}
                </Link>{" "}
                ·{" "}
                <Link href="/signaler" className="ulink">
                  {s.pub.nav.report}
                </Link>
              </p>
            </div>
            <CreateDialog />
          </div>
        </section>
      </main>

      <DossierFooter photos />
    </>
  );
}
