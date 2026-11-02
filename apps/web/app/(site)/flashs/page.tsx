import type { Metadata } from "next";
import { Suspense } from "react";
import { FlashsView } from "@/components/site/public/flashs-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.publicLayer.flashs.title, description: t.publicLayer.flashs.lead };

export default function Page() {
  return (
    <Suspense>
      <FlashsView />
    </Suspense>
  );
}
