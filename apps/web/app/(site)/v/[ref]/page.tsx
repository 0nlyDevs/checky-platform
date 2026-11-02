import type { Metadata } from "next";
import { Suspense } from "react";
import { ShortLink } from "@/components/site/public/short-link";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.site.pub.nav.verified };

export default function Page() {
  return (
    <Suspense>
      <ShortLink />
    </Suspense>
  );
}
