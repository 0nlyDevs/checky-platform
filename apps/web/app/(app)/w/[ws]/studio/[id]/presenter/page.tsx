import { Suspense } from "react";
import { PresenterView } from "@/components/studio/presenter-view";

export default function Page() {
  return (
    <Suspense>
      <PresenterView />
    </Suspense>
  );
}
