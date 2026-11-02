import { AssistantProvider } from "@/components/assistant/assistant-context";
import { StepLine } from "@/components/flow/step-line";
import { SiteHeader } from "@/components/site/site-chrome";
import { t } from "@/lib/i18n/fr";

// The doors into the desk: the form on its card, and beside it what the newsroom does there.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  const a = t.site.auth;
  return (
    <AssistantProvider scope="public">
      <SiteHeader />
      <main className="mx-auto grid max-w-[88rem] gap-12 px-4 pt-10 pb-20 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] lg:gap-20 lg:px-10 lg:pt-16">
        <div className="rounded-md border border-border bg-card p-6 sm:p-8">{children}</div>
        <section className="lg:pt-6" aria-labelledby="auth-side">
          <h2 id="auth-side" className="font-display text-[clamp(2rem,1.4rem+2vw,3.2rem)] leading-[1] font-extrabold tracking-[-0.02em]">
            {a.title}
          </h2>
          <p className="mt-4 max-w-[48ch] text-lg text-pretty text-muted-foreground">{a.lead}</p>
          <StepLine className="mt-10 max-w-md" states={{ claim: "done", evidence: "active", conclusion: "suggested" }} explain />
        </section>
      </main>
    </AssistantProvider>
  );
}
