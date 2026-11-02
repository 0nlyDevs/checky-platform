"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { t } from "@/lib/i18n/fr";

const h = t.site.hero;
const f = t.site.fiche;
const PIECES = h.frames.map((frame, i) => ({ ...frame, src: `/site/dossier/piece-${i + 1}.jpg` }));

/**
 * The title sequence: the reticle follows the night from frame to frame, types each caption and fills
 * the case card, then the stamp lands. Afterwards the visitor holds the reticle.
 */
export function Sequence({ children }: { children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const reticle = useRef<HTMLDivElement>(null);
  const [lit, setLit] = useState(0);
  const [typed, setTyped] = useState<string[]>(PIECES.map(() => ""));
  const [count, setCount] = useState(0);
  const [stamped, setStamped] = useState(false);
  const [clock, setClock] = useState(12);
  const auto = useRef(true);

  useEffect(() => {
    const el = box.current, ret = reticle.current;
    if (!el || !ret) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const aim = (i: number) => {
      const b = el.getBoundingClientRect(), r = el.children[i].getBoundingClientRect();
      ret.style.setProperty("--rx", `${r.left - b.left + r.width / 2}px`);
      ret.style.setProperty("--ry", `${r.top - b.top + (r.height - 30) / 2}px`);
      setLit(i);
    };
    let dead = false;
    const wait = (ms: number) => new Promise((ok) => setTimeout(ok, reduce ? 0 : ms));
    (async () => {
      await wait(600);
      for (let i = 0; i < PIECES.length && !dead; i++) {
        aim(i);
        await wait(600);
        const text = PIECES[i].label;
        for (let c = 1; c <= text.length && !dead; c += reduce ? text.length : 1) {
          setTyped((all) => all.map((v, k) => (k === i ? text.slice(0, c) : v)));
          await wait(16);
        }
        setCount(i + 1);
      }
      if (dead) return;
      aim(0);
      await wait(700);
      setStamped(true);
      auto.current = false;
    })();
    const move = (e: PointerEvent) => {
      if (auto.current || e.pointerType === "touch") return;
      const b = el.getBoundingClientRect();
      ret.style.transition = "transform .12s linear";
      ret.style.setProperty("--rx", `${e.clientX - b.left}px`);
      ret.style.setProperty("--ry", `${e.clientY - b.top}px`);
      [...el.querySelectorAll("figure")].forEach((fig, i) => {
        const r = fig.getBoundingClientRect();
        if (e.clientX > r.left && e.clientX < r.right) setLit(i);
      });
    };
    const leave = () => {
      if (auto.current) return;
      ret.style.transition = "";
      aim(0);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    const tick = setInterval(() => setClock((s) => s + 1), 1000);
    return () => {
      dead = true;
      clearInterval(tick);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
    };
  }, []);

  const m = 47 + Math.floor(clock / 60), s = clock % 60;
  const live = `23:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}`;

  return (
    <>
      <div ref={box} className="dossier-frames" style={{ cursor: "crosshair" }}>
        {PIECES.map((p, i) => (
          <figure key={p.src} className="dossier-frame" data-lit={lit === i}>
            <span className="tc tabular">{i === 0 ? live : p.time}</span>
            <span className="rec" aria-hidden>REC</span>
            <Image src={p.src} alt={p.alt} width={900} height={600} priority={i === 0} sizes="(min-width: 700px) 25vw, 90vw" />
            <figcaption>
              <span aria-label={p.label}>{typed[i] || `Pièce ${i + 1}`}</span>
              <span>CAM {i + 1}</span>
            </figcaption>
          </figure>
        ))}
        <div ref={reticle} className="dossier-reticle" aria-hidden>
          <i />
        </div>
        <span className="stamp" data-on={stamped} aria-hidden data-label={h.stamp} />
      </div>
      <p className="dossier-swipe">← {h.swipe}</p>
      <div className="dossier-title">
        {children}
        <aside className="dossier-fiche" aria-label={`${f.title} · ${t.site.fictional}`}>
          <div className="t">
            <span>{f.title}</span>
            <span>{f.ref}</span>
          </div>
          <dl>
            <dt>{f.rows.claim}</dt>
            <dd>{f.claim}</dd>
            <dt>{f.rows.seen}</dt>
            <dd className="tabular">{f.seen}</dd>
            <dt>{f.rows.pieces}</dt>
            <dd>{f.pieces(count)}</dd>
            <dt>{f.rows.signed}</dt>
            <dd>{stamped ? f.signed : "—"}</dd>
            <dt>{f.rows.verdict}</dt>
            <dd aria-label={stamped ? h.stamp : "—"}>
              <span className="stamp" data-on={stamped} data-label={h.stamp} />
            </dd>
          </dl>
          <p className="typed mt-3.5 text-sm text-ink-soft">{t.site.fictional}</p>
        </aside>
      </div>
    </>
  );
}
