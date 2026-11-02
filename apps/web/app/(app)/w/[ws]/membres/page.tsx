import type { Metadata } from "next";
import { MembersView } from "@/components/members/members-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.members.title };

export default function MembersPage() {
  return <MembersView />;
}
