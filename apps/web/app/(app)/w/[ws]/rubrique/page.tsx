import { Suspense } from "react";
import { RubriqueView } from "@/components/rubrique/rubrique-view";

export default function Page() {
  return (
    <Suspense>
      <RubriqueView />
    </Suspense>
  );
}
