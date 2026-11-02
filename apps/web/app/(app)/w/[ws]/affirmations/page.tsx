import type { Metadata } from "next";
import { ClaimsView } from "@/components/claims/claims-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.claims.title };

export default async function ClaimsPage({ params }: PageProps<"/w/[ws]/affirmations">) {
  const { ws } = await params;
  return <ClaimsView ws={ws} />;
}
