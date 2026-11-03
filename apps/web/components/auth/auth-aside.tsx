"use client";

import { StepLine } from "@/components/flow/step-line";
import { t } from "@/lib/i18n/live";

/** Beside the sign-in and sign-up card: what the newsroom does in the desk, in the chosen language. */
export function AuthAside() {
  const a = t.site.auth;
  return (
    <section className="lg:pt-6" aria-labelledby="auth-side">
      <h2 id="auth-side" className="font-display text-[clamp(2rem,1.4rem+2vw,3.2rem)] leading-[1] font-extrabold tracking-[-0.02em]">
        {a.title}
      </h2>
      <p className="mt-4 max-w-[48ch] text-lg text-pretty text-muted-foreground">{a.lead}</p>
      <StepLine className="mt-10 max-w-md" states={{ claim: "done", evidence: "active", conclusion: "suggested" }} explain />
    </section>
  );
}
