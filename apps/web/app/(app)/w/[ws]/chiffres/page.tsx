import { Suspense } from "react";
import { FiguresView } from "@/components/chiffres/figures-view";

export default function Page() {
  return (
    <Suspense>
      <FiguresView />
    </Suspense>
  );
}
