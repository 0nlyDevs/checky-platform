import type { Metadata } from "next";
import { Suspense } from "react";
import { DeskScanner } from "@/components/scanner/desk-scanner";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.offline.scanner.title };

export default function Page() {
  return (
    <Suspense>
      <DeskScanner />
    </Suspense>
  );
}
