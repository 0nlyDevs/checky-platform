import type { Metadata } from "next";
import { Suspense } from "react";
import { FollowView } from "@/components/site/public/follow-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.site.pub.follow.title };

export default function Page() {
  return (
    <Suspense>
      <FollowView />
    </Suspense>
  );
}
