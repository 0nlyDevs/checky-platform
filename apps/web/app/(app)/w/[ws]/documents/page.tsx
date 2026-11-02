import { Suspense } from "react";
import { SectionTabs } from "@/components/shell/section-tabs";
import { DocumentsView } from "@/components/rubrique/documents-view";

export default function Page() {
  return (
    <Suspense>
      <SectionTabs group="annuaire" />
      <DocumentsView />
    </Suspense>
  );
}
