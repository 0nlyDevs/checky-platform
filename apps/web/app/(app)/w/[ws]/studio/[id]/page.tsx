import { Suspense } from "react";
import { ShowRoom } from "@/components/studio/show-room";
import { SectionTabs } from "@/components/shell/section-tabs";

export default function Page() {
  return (
    <Suspense>
      <SectionTabs group="veille" />
      <ShowRoom />
    </Suspense>
  );
}
