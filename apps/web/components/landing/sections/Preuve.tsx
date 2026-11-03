import { useRef } from "react";
import { ArrowUpRight } from "@phosphor-icons/react";
import { Lines } from "../parts/Lines";
import { gsap, useGSAP, useReducedMotion } from "../lib/motion";

const REASONS = [
  { n: "01", label: "Communiqué officiel N° 045", value: "JIRAMA, 31 oct." },
  { n: "02", label: "Première apparition du reel", value: "Facebook, 23:47" },
  { n: "03", label: "Sources concordantes", value: "4, dont 2 officielles" },
  { n: "04", label: "Démenti publié par la source", value: "Manquant", missing: true },
];

export function Preuve() {
  const root = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      const num = root.current!.querySelector<HTMLElement>(".preuve-pct b")!;
      if (reduce) {
        num.textContent = "92";
        return;
      }
      const c = { v: 0 };
      gsap.to(c, {
        v: 92,
        duration: 1.8,
        ease: "power3.out",
        scrollTrigger: { trigger: num, start: "top 80%", once: true },
        onUpdate: () => {
          num.textContent = String(Math.round(c.v));
        },
      });
    },
    { scope: root, dependencies: [reduce] },
  );

  return (
    <section ref={root} id="preuve" className="section wrap">
      <div className="section-head">
        <Lines
          className="display h2"
          lines={[
            "Le pourcentage",
            <>
              vient des <em>preuves</em>.
            </>,
          ]}
        />
        <p className="lead" data-reveal="fade" style={{ marginTop: 28 }}>
          Jamais du modèle. Chaque carte liste ce qui a été trouvé, ce qui manque, et montre le faux à côté de l’original.
        </p>
      </div>
      <div className="preuve-grid">
        <div data-reveal="fade">
          <div className="preuve-pct">
            <b>0</b>
            <small>%</small>
          </div>
          <div className="preuve-level">
            <i />
            Faux, confiance élevée
          </div>
        </div>
        <div>
          <ol className="reasons" data-reveal="stagger">
            {REASONS.map((r) => (
              <li key={r.n} className={r.missing ? "is-missing" : ""}>
                <span className="r-n">{r.n}</span>
                <span>{r.label}</span>
                <span className="r-v">{r.value}</span>
              </li>
            ))}
          </ol>
          <div className="diff panel" data-reveal="fade">
            <div className="diff-head">
              <span className="mono">Reel, 23:47</span>
              <span className="mono">Communiqué N° 045</span>
            </div>
            <p className="diff-text">
              Coupures de <del>72 heures</del> <ins>4 heures</ins> dès <del>demain</del> <ins>mardi, de 20 h à minuit</ins> dans tout Toamasina.
            </p>
            <div className="diff-foot">
              <span className="btn btn-ghost" style={{ height: 44, padding: "0 20px" }}>
                Partager la carte
                <ArrowUpRight className="arrow" size={16} weight="bold" />
              </span>
              <span className="mono">Image 1080 par 1350, prête pour WhatsApp</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
