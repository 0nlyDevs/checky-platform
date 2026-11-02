import type { Metadata } from "next";
import { Suspense } from "react";
import { SectionTabs } from "@/components/shell/section-tabs";
import { ClaimsView } from "@/components/claims/claims-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.claims.title };

// The view reads the workspace and the chosen view from the URL on the client, so the shell stays instant.
export default function ClaimsPage() {
  return (
    <Suspense>
      <SectionTabs group="affirmations" />
      <ClaimsView />
    </Suspense>
  );
}
