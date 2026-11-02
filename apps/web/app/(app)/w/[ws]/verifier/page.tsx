import type { Metadata } from "next";
import { Suspense } from "react";
import { VerifyView } from "@/components/verify/verify-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.nav.check };

export default function VerifyPage() {
  return (
    <Suspense>
      <VerifyView />
    </Suspense>
  );
}
