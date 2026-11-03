import { Suspense } from "react";
import { VeilleView } from "@/components/veille/veille-view";

export default function Page() {
  return (
    <Suspense>
      <VeilleView />
    </Suspense>
  );
}
