import type { Metadata } from "next";
import { Suspense } from "react";
import { ReponseView } from "@/components/dossier/reponse-view";
import { t } from "@/lib/i18n/fr";

// A private link sent to one person: never indexed.
export const metadata: Metadata = { title: t.dossier.reponse.title, robots: { index: false, follow: false } };

export default function Page() {
  return (
    <Suspense>
      <ReponseView />
    </Suspense>
  );
}
