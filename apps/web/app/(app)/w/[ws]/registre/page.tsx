import { Suspense } from "react";
import { RegistryView } from "@/components/registre/registry-view";

export default function Page() {
  return (
    <Suspense>
      <RegistryView />
    </Suspense>
  );
}
