import { Suspense } from "react";
import { StudioView } from "@/components/studio/studio-view";
import { SectionTabs } from "@/components/shell/section-tabs";

export default function Page() {
  return (
    <Suspense>
      <SectionTabs group="veille" />
      <StudioView />
    </Suspense>
  );
}
