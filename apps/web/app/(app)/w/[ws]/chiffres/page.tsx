import { Suspense } from "react";
import { SectionTabs } from "@/components/shell/section-tabs";
import { FiguresView } from "@/components/chiffres/figures-view";

export default function Page() {
  return (
    <Suspense>
      <SectionTabs group="annuaire" />
      <FiguresView />
    </Suspense>
  );
}
