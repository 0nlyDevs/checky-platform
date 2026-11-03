import { useRef } from "react";
import { ROUTE } from "../content/site";
import { Lines } from "../parts/Lines";
import { gsap, useGSAP, useReducedMotion } from "../lib/motion";

const XS = [90, 430, 770, 1110];
const Y1 = 100;
const Y2 = 300;

function path(y: number) {
  return `M ${XS[0]} ${y} C ${XS[0] + 170} ${y - 50}, ${XS[1] - 170} ${y + 50}, ${XS[1]} ${y} S ${XS[2] - 170} ${y - 50}, ${XS[2]} ${y} S ${XS[3] - 170} ${y + 50}, ${XS[3]} ${y}`;
}

export function Trajet() {
  const root = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();

  useGSAP(
    () => {
      const el = root.current!;
      const paths = el.querySelectorAll<SVGPathElement>(".t-path");
      const nodes = [el.querySelectorAll<SVGGElement>(".t-node-1"), el.querySelectorAll<SVGGElement>(".t-node-2")];
      if (reduce) return;
      const tl = gsap.timeline({
        scrollTrigger: { trigger: el.querySelector(".trajet-svg"), start: "top 78%", end: "bottom 55%", scrub: 0.7 },
      });
      paths.forEach((p, i) => {
        const len = p.getTotalLength();
        gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
        tl.to(p, { strokeDashoffset: 0, duration: 1, ease: "none" }, i * 1.1);
        tl.fromTo(
          nodes[i],
          { opacity: 0, scale: 0.6, transformOrigin: "50% 50%" },
          { opacity: 1, scale: 1, duration: 0.2, stagger: 0.26, ease: "back.out(2)" },
          i * 1.1 + 0.02,
        );
      });
    },
    { scope: root, dependencies: [reduce] },
  );

  return (
    <section ref={root} id="trajet" className="section wrap">
      <div className="section-head">
        <Lines
          className="display h2"
          lines={[
            "La vérité doit faire",
            <>
              le même <em>trajet</em>.
            </>,
          ]}
        />
        <p className="lead" data-reveal="fade" style={{ marginTop: 28 }}>
          Un démenti qui reste sur le site du journal ne rattrape rien. Checky renvoie la carte par les canaux que la rumeur a pris.
        </p>
      </div>
      <svg className="trajet-svg" viewBox="0 0 1200 400" aria-labelledby="trajet-title" role="img">
        <title id="trajet-title">Le trajet de la rumeur, puis le trajet du démenti par les mêmes canaux</title>
        <text x={XS[0]} y={Y1 - 58} className="t-label">
          La rumeur
        </text>
        <text x={XS[0]} y={Y2 - 58} className="t-label">
          Le démenti, mêmes canaux
        </text>
        <path className="t-path" d={path(Y1)} fill="none" stroke="rgba(243,242,238,0.35)" strokeWidth={1.5} strokeDasharray="6 8" />
        <path className="t-path" d={path(Y2)} fill="none" stroke="#f3f2ee" strokeWidth={2} />
        {ROUTE.rumeur.map((s, i) => (
          <g key={s.label} className="t-node-1">
            <circle cx={XS[i]} cy={Y1} r={7} fill="#0a0a0b" stroke="rgba(243,242,238,0.5)" strokeWidth={1.5} />
            <text x={XS[i]} y={Y1 - 24} textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"} className="t-time">
              {s.time}
            </text>
            <text x={XS[i]} y={Y1 + 34} textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}>
              {s.label}
            </text>
          </g>
        ))}
        {ROUTE.verite.map((s, i) => (
          <g key={s.label} className="t-node-2">
            <circle cx={XS[i]} cy={Y2} r={8} fill="#f3f2ee" />
            <text x={XS[i]} y={Y2 - 24} textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"} className="t-time">
              {s.time}
            </text>
            <text x={XS[i]} y={Y2 + 34} textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}>
              {s.label}
            </text>
          </g>
        ))}
      </svg>
      <div className="trajet-list" data-reveal="stagger">
        <div>
          <span className="mono">La rumeur</span>
          <ol>
            {ROUTE.rumeur.map((s) => (
              <li key={s.label}>
                <span>{s.label}</span>
                <span className="mono">{s.time}</span>
              </li>
            ))}
          </ol>
        </div>
        <div>
          <span className="mono">Le démenti, mêmes canaux</span>
          <ol>
            {ROUTE.verite.map((s) => (
              <li key={s.label}>
                <span>{s.label}</span>
                <span className="mono">{s.time}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <p className="trajet-sum display" data-reveal="fade" style={{ fontWeight: 600 }}>
        La carte repart par WhatsApp, à l’antenne, par SMS et sur l’affiche du fokontany. Là où la rumeur est passée.
      </p>
    </section>
  );
}
