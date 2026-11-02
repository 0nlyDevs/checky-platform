import type { Metadata } from "next";
import { ClaimDetail } from "@/components/claims/claim-detail";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.claims.title };

export default function ClaimPage() {
  return <ClaimDetail />;
}
