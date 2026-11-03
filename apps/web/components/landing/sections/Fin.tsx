import Link from "next/link";
import { ArrowUpRight } from "@phosphor-icons/react";
import { ROUTES } from "../content/site";
import { Lines } from "../parts/Lines";
import { Magnetic } from "../parts/Magnetic";
import { scrollToId } from "../lib/motion";

const COLS = [
  {
    title: "Produit",
    links: [
      { label: "Appli Android", href: ROUTES.android },
      { label: "Extension navigateur", href: "#partout" },
      { label: "SMS 142", href: "#partout" },
    ],
  },
  {
    title: "Méthode",
    links: [
      { label: "Les quatre verdicts", href: "#verdict" },
      { label: "La preuve", href: "#preuve" },
      { label: "Le trajet du démenti", href: "#trajet" },
    ],
  },
  {
    title: "Sans compte",
    links: [
      { label: "Est-ce déjà vérifié ?", href: ROUTES.verified },
      { label: "Signaler une rumeur", href: ROUTES.report },
      { label: "Créer une rédaction", href: ROUTES.signUp },
    ],
  },
];

export function Fin() {
  const go = (href: string) => (e: React.MouseEvent) => {
    if (!href.startsWith("#")) return;
    e.preventDefault();
    scrollToId(href.slice(1));
  };
  return (
    <footer id="fin" className="fin section">
      <div className="wrap">
        <Lines
          className="display h2"
          lines={[
            "Allumez",
            <>
              la <em>torche</em>.
            </>,
          ]}
        />
        <p className="lead" data-reveal="fade" style={{ marginTop: 28 }}>
          Checky est gratuit pour les journalistes de Madagascar. Ouvrez-le dans le navigateur ou installez l’appli Android. Sans compte, vérifiez une info ou
          signalez une rumeur.
        </p>
        <div className="fin-cta" data-reveal="stagger">
          <Magnetic>
            <Link className="btn btn-fill" href={ROUTES.signIn}>
              Ouvrir Checky
              <ArrowUpRight className="arrow" size={18} weight="bold" />
            </Link>
          </Magnetic>
          <Magnetic strength={0.25}>
            <a className="btn btn-ghost" href={ROUTES.android} rel="noreferrer">
              Installer l’appli Android
            </a>
          </Magnetic>
          <Magnetic strength={0.25}>
            <Link className="btn btn-ghost" href={ROUTES.verified}>
              Vérifier une info
            </Link>
          </Magnetic>
        </div>
        <div className="fin-grid" data-reveal="stagger">
          <div>
            <span style={{ fontWeight: 800, letterSpacing: "-0.05em", fontSize: "1.3rem" }}>CHECKY</span>
            <p className="lead" style={{ fontSize: "0.95rem", marginTop: 12, maxWidth: "30ch" }}>
              La torche du journaliste. Malagasy, français, anglais.
            </p>
          </div>
          {COLS.map((c) => (
            <div key={c.title}>
              <span className="mono">{c.title}</span>
              <ul>
                {c.links.map((l) => (
                  <li key={l.label}>
                    {l.href.startsWith("/") ? (
                      <Link href={l.href}>{l.label}</Link>
                    ) : (
                      <a href={l.href} onClick={go(l.href)}>
                        {l.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="fin-legal mono">
          <span>2026 Checky, hackathon Fanilo</span>
          <span>Antananarivo, Madagascar</span>
          <a href="/site/landing/videos/CREDITS.md" target="_blank" rel="noreferrer">
            Crédits vidéo, Wikimedia Commons
          </a>
        </div>
      </div>
      <div className="fin-ghost" aria-hidden>
        <svg viewBox="0 0 1000 245" focusable="false">
          <defs>
            <linearGradient id="fin-wordmark-glow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="35%" stopColor="white" stopOpacity="0" />
              <stop offset="70%" stopColor="white" stopOpacity="0.3" />
              <stop offset="100%" stopColor="white" />
            </linearGradient>
          </defs>
          <text x="0" y="232" textLength="1000" lengthAdjust="spacingAndGlyphs">CHECKY</text>
          <text className="fin-ghost-bloom" x="0" y="232" textLength="1000" lengthAdjust="spacingAndGlyphs">CHECKY</text>
        </svg>
      </div>
    </footer>
  );
}
