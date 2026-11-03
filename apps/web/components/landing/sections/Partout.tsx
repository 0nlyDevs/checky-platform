import { useRef } from "react";
import { Check, X } from "@phosphor-icons/react";
import { EXTENSION_GESTURES, PHONE_GESTURES } from "../content/site";
import { Gesture } from "../parts/Gesture";
import { Lines } from "../parts/Lines";
import { gsap, ScrollTrigger, useGSAP, useReducedMotion } from "../lib/motion";

const STEPS = [
  { n: "01", label: "Source d’origine trouvée", value: "Facebook, 23:47" },
  { n: "02", label: "Communiqué N° 045 lu", value: "JIRAMA" },
  { n: "03", label: "Chiffres comparés", value: "72 h contre 4 h" },
  { n: "04", label: "Sources concordantes", value: "4" },
];

export function Partout() {
  const root = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      const el = root.current!;
      const steps = el.querySelectorAll<HTMLElement>(".card-steps li");
      const verdict = el.querySelector<HTMLElement>(".card-verdict")!;
      const mark = el.querySelector<HTMLElement>(".ext-post mark")!;
      const menu = el.querySelector<HTMLElement>(".ext-menu")!;
      const note = el.querySelector<HTMLElement>(".ext-note")!;
      if (reduce) {
        steps.forEach((s) => s.classList.add("is-done"));
        verdict.classList.add("is-solid");
        mark.classList.add("is-on");
        gsap.set([menu, note], { opacity: 1, y: 0 });
        return;
      }
      ScrollTrigger.create({
        trigger: el.querySelector(".is-phone"),
        start: "top 70%",
        end: "bottom 70%",
        onUpdate: (st) => {
          steps.forEach((s, i) => s.classList.toggle("is-done", st.progress > 0.12 + i * 0.16));
          verdict.classList.toggle("is-solid", st.progress > 0.8);
        },
      });
      gsap
        .timeline({ scrollTrigger: { trigger: el.querySelector(".is-ext"), start: "top 70%", end: "bottom 75%", scrub: 0.6 } })
        .add(() => mark.classList.toggle("is-on"), 0.3)
        .to(menu, { opacity: 1, y: 0, duration: 0.2, ease: "power2.out" }, 0.45)
        .to(menu, { opacity: 0, y: -4, duration: 0.15, ease: "power2.in" }, 0.75)
        .to(note, { opacity: 1, y: 0, duration: 0.25, ease: "power2.out" }, 0.8);
    },
    { scope: root, dependencies: [reduce] },
  );

  return (
    <section ref={root} id="partout" className="section wrap">
      <div className="section-head">
        <Lines
          className="display h2"
          lines={[
            "Dans la poche,",
            <>
              dans le <em>navigateur</em>.
            </>,
          ]}
        />
        <p className="lead" data-reveal="fade" style={{ marginTop: 28 }}>
          Une appli Android pour le terrain, une extension pour le bureau. Même verdict, même preuve, même carte à partager.
        </p>
      </div>
      <div className="partout-grid">
        <article className="panel device-panel is-phone" data-reveal="fade">
          <div className="device-copy">
            <span className="mono">Appli Android</span>
            <h3 className="display h3">Le terrain, sans réseau.</h3>
            <ul className="gestures">
              {PHONE_GESTURES.map((g) => (
                <Gesture key={g.title} {...g} />
              ))}
            </ul>
          </div>
          <div className="device-stage">
            <div className="phone" aria-hidden>
              <div className="phone-screen">
                <span className="phone-notch" />
                <div className="card">
                  <div className="card-top">
                    <span className="card-chip">Partagé depuis TikTok</span>
                    <span className="mono">00:14</span>
                  </div>
                  <p className="card-claim">« 72 heures de délestage dès demain à Toamasina »</p>
                  <ul className="card-steps">
                    {STEPS.map((s) => (
                      <li key={s.n}>
                        <span className="ok">
                          <Check size={10} weight="bold" />
                        </span>
                        <span>{s.label}</span>
                        <b>{s.value}</b>
                      </li>
                    ))}
                  </ul>
                  <div className="card-verdict">
                    <span className="v-icon">
                      <X size={16} weight="bold" />
                    </span>
                    <div>
                      <strong>Faux, 92 %</strong>
                      <small>4 sources, 2 officielles</small>
                    </div>
                  </div>
                  <p className="card-diff">
                    Coupures de <del>72 heures</del> <ins>4 heures</ins>, mardi de 20 h à minuit.
                  </p>
                  <div className="card-btns">
                    <span className="card-btn">Partager</span>
                    <span className="card-btn is-off">Confirmer</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>
        <article className="panel device-panel is-ext" data-reveal="fade">
          <div className="device-copy">
            <span className="mono">Extension navigateur</span>
            <h3 className="display h3">Le bureau, sans quitter la page.</h3>
            <ul className="gestures">
              {EXTENSION_GESTURES.map((g) => (
                <Gesture key={g.title} {...g} />
              ))}
            </ul>
          </div>
          <div className="device-stage">
            <div className="ext" aria-hidden>
              <div className="ext-bar">
                <i />
                <i />
                <i />
                <span className="ext-url">facebook.com/groups/toamasina-info</span>
              </div>
              <div className="ext-body">
                <p className="ext-post">
                  Attention à tous : <mark>72 heures de délestage dès demain</mark> dans toute la ville, partagez vite à vos proches.
                </p>
                <div className="ext-menu">Vérifier avec Checky</div>
                <div className="ext-note">
                  <span className="v-icon">
                    <X size={14} weight="bold" />
                  </span>
                  <div>
                    <strong>Faux, 92 %</strong>
                    <span>
                      Le communiqué N° 045 annonce quatre heures, mardi de 20 h à minuit. <a href="#preuve">Voir la carte</a>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
