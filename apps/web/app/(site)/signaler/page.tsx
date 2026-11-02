import type { Metadata } from "next";
import { Suspense } from "react";
import { ReportView } from "@/components/site/public/report-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.site.pub.report.title };

export default function Page() {
  return (
    <Suspense>
      <ReportView />
    </Suspense>
  );
}
