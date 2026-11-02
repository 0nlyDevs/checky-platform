import { Suspense } from "react";
import { DocumentsView } from "@/components/rubrique/documents-view";

export default function Page() {
  return (
    <Suspense>
      <DocumentsView />
    </Suspense>
  );
}
