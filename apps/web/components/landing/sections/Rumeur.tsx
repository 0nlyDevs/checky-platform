import { useEffect, useRef } from "react";
import { REEL_CLIP } from "../content/hero";
import { drawPlaceholder } from "../three/clipSources";
import { ROUTE } from "../content/site";
import { gsap, ScrollTrigger, useGSAP, useReducedMotion } from "../lib/motion";

const STOPS = [
  {
    ...ROUTE.rumeur[0],
    text: "Un reel de quatorze secondes : « 72 heures de délestage dès demain ». Un logo découpé, une voix pressée.",
    stats: [
      { n: "312", l: "partages avant minuit" },
      { n: "1", l: "source, anonyme" },
    ],
  },
  {
    ...ROUTE.rumeur[1],
    text: "Le reel entre dans les groupes de quartier. Les captures d’écran remplacent la vidéo. Le logo devient flou.",
    stats: [
      { n: "41", l: "groupes touchés" },
      { n: "0", l: "communiqué cité" },
    ],
  },
  {
    ...ROUTE.rumeur[2],
    text: "Une radio régionale lit la rumeur à l’antenne, au conditionnel. Pour des milliers d’auditeurs, le conditionnel ne s’entend pas.",
    stats: [
      { n: "6", l: "régions atteintes" },
      { n: "1", l: "antenne qui la lit" },
    ],
  },
  {
    ...ROUTE.rumeur[3],
    text: "Au sud-ouest, la rumeur arrive par SMS, sans vidéo, sans logo. Juste la phrase, et le mot « urgent ».",
    stats: [
      { n: "9 h", l: "sans démenti" },
      { n: "24", l: "régions à prévenir" },
    ],
  },
];

export function Rumeur() {
  const root = useRef<HTMLElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const poster = useRef<HTMLCanvasElement>(null);

  // Poster of the rumour reel, drawn like the galaxy's cards. The hero's 3D
  // scene lays the picked card over it; without WebGL the poster stays.
  useEffect(() => {
    const c = poster.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    const draw = () => drawPlaceholder(ctx, c.width, c.height, REEL_CLIP, 0);
    draw();
    document.fonts?.ready.then(draw);
  }, []);

  useGSAP(
    () => {
      if (reduce) return;
      const section = root.current!;
      const el = track.current!;
      const bar = section.querySelector<HTMLElement>(".rumeur-bar i")!;
      const size = () => {
        section.style.height = `${el.scrollWidth - window.innerWidth + window.innerHeight}px`;
      };
      size();
      const onInit = () => size();
      ScrollTrigger.addEventListener("refreshInit", onInit);
      const tween = gsap.to(el, {
        x: () => -(el.scrollWidth - window.innerWidth),
        ease: "none",
        scrollTrigger: {
          trigger: section,
          start: "top top",
          end: "bottom bottom",
          scrub: 0.8,
          invalidateOnRefresh: true,
          onUpdate: (st) => {
            bar.style.transform = `scaleX(${st.progress})`;
          },
        },
      });
      gsap.utils.toArray<HTMLElement>(".slide").forEach((slide, i) => {
        const items = slide.querySelectorAll<HTMLElement>("[data-in]");
        if (!items.length) return;
        gsap.fromTo(
          items,
          { y: 48, opacity: 0 },
          {
            y: 0,
            opacity: 1,
            duration: 0.9,
            stagger: 0.1,
            ease: "power3.out",
            scrollTrigger:
              i === 0 ? { trigger: slide, start: "top 96%", once: true } : { trigger: slide, containerAnimation: tween, start: "left 78%", once: true },
          },
        );
      });
      return () => ScrollTrigger.removeEventListener("refreshInit", onInit);
    },
    { scope: root, dependencies: [reduce] },
  );

  return (
    <section ref={root} id="rumeur" className="rumeur section">
      <div ref={track} className="rumeur-track" data-reel-track>
        <div className="slide is-head">
          <div className="head-copy">
            <h2 className="display h2" data-in>
              La rumeur voyage plus vite que la <em>vérité</em>.
            </h2>
            <p className="lead" data-in>
              Une nuit, une île. Suivez un faux communiqué de Facebook jusqu’aux SMS du sud-ouest, de 23:47 à 08:15.
            </p>
          </div>
          <figure className="reel">
            <div className="reel-slot" data-reel-slot>
              {REEL_CLIP.src ? (
                <video src={REEL_CLIP.src} muted loop playsInline autoPlay preload="metadata" aria-hidden />
              ) : (
                <canvas ref={poster} width={640} height={360} aria-hidden />
              )}
            </div>
            <figcaption className="mono">Facebook, 23:47 · 14 s · logo découpé</figcaption>
          </figure>
        </div>
        {STOPS.map((s, i) => (
          <article className="slide" key={s.label}>
            <div className="slide-time" data-in>
              {s.time}
            </div>
            <div className="slide-place mono" data-in>
              {String(i + 1).padStart(2, "0")} {s.label}
            </div>
            <p className="slide-text" data-in>
              {s.text}
            </p>
            <div className="slide-stats" data-in>
              {s.stats.map((st) => (
                <div key={st.l}>
                  <div className="stat-num">{st.n}</div>
                  <div className="mono">{st.l}</div>
                </div>
              ))}
            </div>
          </article>
        ))}
        <article className="slide is-end">
          <div className="slide-time" data-in>
            06:41
          </div>
          <div className="slide-place mono" data-in>
            Checky, carte verdict
          </div>
          <p className="slide-text" data-in>
            Une journaliste partage le reel vers Checky. Le vrai communiqué dit quatre heures. La carte part sur WhatsApp avant la radio de 07:00.
          </p>
          <div className="slide-stats" data-in>
            <div>
              <div className="stat-num">92 %</div>
              <div className="mono">Faux, preuves à l’appui</div>
            </div>
            <div>
              <div className="stat-num">4</div>
              <div className="mono">Sources, deux officielles</div>
            </div>
          </div>
        </article>
      </div>
      <div className="rumeur-bar" aria-hidden>
        <i />
      </div>
    </section>
  );
}
