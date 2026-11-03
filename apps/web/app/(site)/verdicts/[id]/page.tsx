import type { Metadata } from "next";
import { Suspense } from "react";
import { VerdictPage } from "@/components/site/public/verdict-page";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.site.pub.nav.verified };

export default function Page() {
  return (
    <Suspense>
      <VerdictPage />
    </Suspense>
  );
}
