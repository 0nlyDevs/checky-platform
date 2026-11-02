import type { Metadata } from "next";
import { Suspense } from "react";
import { VerifyView } from "@/components/verify/verify-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.nav.check };

// « Analyser un lien » now lives inside Vérifier; this address (used by the copilot's
// open_link_check with ?lien=) shows the same screen.
export default function LinkCheckPage() {
  return (
    <Suspense>
      <VerifyView />
    </Suspense>
  );
}
