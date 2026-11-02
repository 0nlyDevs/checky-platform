import type { Metadata } from "next";
import { VerifiesView } from "@/components/site/public/verifies-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.site.pub.nav.verified };

export default function Page() {
  return <VerifiesView />;
}
