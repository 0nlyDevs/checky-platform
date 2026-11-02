import type { Metadata } from "next";
import { Suspense } from "react";
import { DossierMotion } from "@/components/site/dossier/motion";
import { DossierFooter } from "@/components/site/public/dossier-footer";
import { FollowView } from "@/components/site/public/follow-view";
import { SiteHeader } from "@/components/site/public/site-header";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.site.pub.follow.title };

export default function Page() {
  return (
    <>
      <DossierMotion />
      <SiteHeader />
      <main id="contenu">
        <Suspense>
          <FollowView />
        </Suspense>
      </main>
      <DossierFooter />
    </>
  );
}
