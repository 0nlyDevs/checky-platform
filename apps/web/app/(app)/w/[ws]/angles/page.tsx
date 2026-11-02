import { Suspense } from "react";
import { AnglesView } from "@/components/rubrique/angles-view";

export default function Page() {
  return (
    <Suspense>
      <AnglesView />
    </Suspense>
  );
}
