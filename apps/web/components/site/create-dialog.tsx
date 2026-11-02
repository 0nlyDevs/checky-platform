"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { t } from "@/lib/i18n/fr";

// Read by the onboarding (app/(app)/page.tsx) once the visitor has signed up.
const DRAFT = "fanilo:workspace";

/** The opening card: name the newsroom, choose demo or empty, and the card takes its stamp before sign-up. */
export function CreateDialog() {
  const d = t.site.close.dialog;
  const router = useRouter();
  const [name, setName] = useState<string>(d.example);
  const [demo, setDemo] = useState(true);
  const [stamped, setStamped] = useState(false);

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      sessionStorage.setItem(DRAFT, JSON.stringify({ name: name.trim() || d.example, demo }));
    } catch {
      // Without storage the onboarding simply starts empty.
    }
    setStamped(true);
    setTimeout(() => router.push("/inscription"), matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650);
  }

  return (
    <form onSubmit={submit} className="dossier-card" aria-labelledby="open-card-title">
      <p id="open-card-title" className="t">
        {d.title}
      </p>
      <label htmlFor="landing-ws">{d.label}</label>
      <input id="landing-ws" type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
      <fieldset>
        <legend>{d.start}</legend>
        <div className="choice">
          <label>
            <input type="radio" name="demo" checked={demo} onChange={() => setDemo(true)} /> {d.demo}
          </label>
          <label>
            <input type="radio" name="demo" checked={!demo} onChange={() => setDemo(false)} /> {d.empty}
          </label>
        </div>
      </fieldset>
      <button type="submit" className="tab-btn">
        {d.submit} <span className="arr" aria-hidden>→</span>
      </button>
      <span className="stamp" data-on={stamped} aria-hidden data-label={d.stamp} />
    </form>
  );
}
