import type { Metadata } from "next";
import { Suspense } from "react";
import { LinkCheckView } from "@/components/linkcheck/link-check-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.linkCheck.title };

export default function LinkCheckPage() {
  return (
    <Suspense>
      <LinkCheckView />
    </Suspense>
  );
}
