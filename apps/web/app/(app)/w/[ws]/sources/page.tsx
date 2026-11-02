import type { Metadata } from "next";
import { Suspense } from "react";
import { SourcesView } from "@/components/sources/sources-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.sources.title };

export default function SourcesPage() {
  // useSearchParams (the tab) must sit inside a Suspense boundary with cacheComponents.
  return (
    <Suspense>
      <SourcesView />
    </Suspense>
  );
}
