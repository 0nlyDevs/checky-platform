import { Suspense } from "react";
import { SectionTabs } from "@/components/shell/section-tabs";
import { RegistryView } from "@/components/registre/registry-view";

export default function Page() {
  return (
    <Suspense>
      <SectionTabs group="annuaire" />
      <RegistryView />
    </Suspense>
  );
}
