"use client";

import { useEffect, useRef, useState } from "react";
import { Preloader } from "./parts/Preloader";
import { Rail } from "./parts/Rail";
import { Wordmark } from "./parts/Wordmark";
import { useReveals } from "./parts/useReveals";
import { destroyScroll, initScroll, ScrollTrigger, useReducedMotion } from "./lib/motion";
import { HeroGalaxie } from "./sections/HeroGalaxie";
import { Rumeur } from "./sections/Rumeur";
import { Besoins } from "./sections/Besoins";
import { Verdict } from "./sections/Verdict";
import { Preuve } from "./sections/Preuve";
import { Trajet } from "./sections/Trajet";
import { Partout } from "./sections/Partout";
import { Fin } from "./sections/Fin";
import "./styles/global.css";

/**
 * The public landing (`/accueil`, shown at `/` to signed-out visitors): the
 * galaxy hero, then the rumour's road chapter by chapter, with the section
 * ruler on the right. Every style is scoped under `.landing`.
 */
export function Landing() {
  const root = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const html = document.documentElement;
    html.classList.add("on-landing");
    return () => html.classList.remove("on-landing");
  }, []);

  useEffect(() => {
    const el = root.current;
    if (reduce || !el) return;
    initScroll(el);
    const onLoad = () => ScrollTrigger.refresh();
    window.addEventListener("load", onLoad);
    document.fonts.ready.then(onLoad);
    return () => {
      window.removeEventListener("load", onLoad);
      destroyScroll(el);
    };
  }, [reduce]);

  useReveals(ready, reduce);

  return (
    <div ref={root} className="landing">
      <Preloader onDone={() => setReady(true)} />
      <Wordmark />
      <Rail ready={ready} heroWord />
      <main id="main">
        <HeroGalaxie ready={ready} />
        <Rumeur />
        <Besoins />
        <Verdict />
        <Preuve />
        <Trajet />
        <Partout />
        <Fin />
      </main>
      <div className="grain" aria-hidden />
    </div>
  );
}
