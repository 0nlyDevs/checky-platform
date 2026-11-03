import { useRef, useState } from "react";
import { Check } from "@phosphor-icons/react";
import { NEEDS } from "../content/site";
import { Lines } from "../parts/Lines";
import { ScrollTrigger, useGSAP } from "../lib/motion";

export function Besoins() {
  const root = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);

  useGSAP(
    () => {
      const triggers = Array.from(root.current!.querySelectorAll<HTMLElement>(".need")).map((need, i) =>
        ScrollTrigger.create({
          trigger: need,
          start: "top 55%",
          end: "bottom 55%",
          onToggle: (st) => {
            if (st.isActive) setActive(i);
          },
        }),
      );
      return () => triggers.forEach((t) => t.kill());
    },
    { scope: root },
  );

  return (
    <section ref={root} id="besoins" className="section wrap">
      <div className="section-head">
        <Lines
          className="display h2"
          lines={[
            "Huit besoins,",
            <>
              dits par <em>vous</em>.
            </>,
          ]}
        />
        <p className="lead" data-reveal="fade" style={{ marginTop: 28 }}>
          Les journalistes de Madagascar ont nommé leurs manques. Chaque besoin a sa réponse dans la carte verdict, pas dans un menu.
        </p>
      </div>
      <div className="besoins-grid">
        <aside className="besoins-side" aria-hidden>
          <div>
            <div className="besoins-count">
              {NEEDS[active].n}
              <small> / 08</small>
            </div>
            <div className="besoins-quote">
              {NEEDS.map((need, i) => (
                <p key={need.n} className={i === active ? "is-on" : ""} style={{ transition: "opacity 0.45s ease" }}>
                  « {need.quote} »
                </p>
              ))}
            </div>
          </div>
          <div className="ticks">
            {NEEDS.map((need, i) => (
              <span key={need.n} className={`tick${i <= active ? " is-done" : ""}`}>
                <Check size={12} weight="bold" />
              </span>
            ))}
          </div>
        </aside>
        <ol className="besoins-list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {NEEDS.map((need, i) => (
            <li key={need.n} className={`need${i === active ? " is-active" : ""}`}>
              <div className="need-n mono">
                <span>{need.n}</span>
              </div>
              <h3 className="display h3 need-title" style={{ margin: 0 }}>
                {need.title}
              </h3>
              <p className="need-quote">« {need.quote} »</p>
              <p className="need-answer lead">{need.answer}</p>
            </li>
          ))}
        </ol>
      </div>
      <div className="besoins-final">
        <Lines
          as="h3"
          className="display h3"
          lines={[
            "Un seul geste couvre les huit.",
            <>
              Partagez, Checky <em>répond</em>.
            </>,
          ]}
        />
      </div>
    </section>
  );
}
