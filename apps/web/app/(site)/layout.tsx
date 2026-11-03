import { AssistantProvider } from "@/components/assistant/assistant-context";
import { LangScope } from "@/components/prefs/lang-scope";
import { SiteFooter, SiteHeader } from "@/components/site/site-chrome";
import { t } from "@/lib/i18n/fr";
import "@/components/site/site.css";

// Public pages: the visitor's three places under one bar; the guide docks beside the page.
export default function SiteLayout({ children }: LayoutProps<"/">) {
  return (
    <AssistantProvider scope="public">
      <a
        href="#contenu"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-foreground focus:px-3 focus:py-2 focus:text-background"
      >
        {t.nav.skip}
      </a>
      <div className="flex min-h-dvh flex-col">
        <SiteHeader />
        <main id="contenu" className="flex-1">
          {/* Some views read the live `t` (the official feed, the reply page, the numbered line):
              LangScope remounts them on a language switch, as on the desk and the sign-in pages. */}
          <LangScope>{children}</LangScope>
        </main>
        <SiteFooter />
      </div>
    </AssistantProvider>
  );
}
