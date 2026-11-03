import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AuthAside } from "@/components/auth/auth-aside";
import { LangScope } from "@/components/prefs/lang-scope";
import { SiteHeader } from "@/components/site/site-chrome";

// The doors into the desk: the form on its card, and beside it what the newsroom does there.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <AssistantProvider scope="public">
      <SiteHeader />
      <LangScope>
        <main className="mx-auto grid max-w-[88rem] gap-12 px-4 pt-10 pb-20 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] lg:gap-20 lg:px-10 lg:pt-16">
          <div className="rounded-md border border-border bg-card p-6 sm:p-8">{children}</div>
          <AuthAside />
        </main>
      </LangScope>
    </AssistantProvider>
  );
}
