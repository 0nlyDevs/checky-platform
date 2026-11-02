import type { Metadata } from "next";
import { Suspense } from "react";
import { SealCheck } from "@/components/registre/seal-check";
import { registre } from "@/lib/i18n/fr/registre";

export const metadata: Metadata = { title: registre.check.title };

export default function Page() {
  return (
    <Suspense>
      <SealCheck />
    </Suspense>
  );
}
