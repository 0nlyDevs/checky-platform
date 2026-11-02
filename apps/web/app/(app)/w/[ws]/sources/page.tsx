import type { Metadata } from "next";
import { SourcesView } from "@/components/sources/sources-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.sources.title };

export default function SourcesPage() {
  return <SourcesView />;
}
