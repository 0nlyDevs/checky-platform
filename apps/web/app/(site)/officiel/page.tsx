import type { Metadata } from "next";
import { OfficialFeed } from "@/components/registre/official-feed";
import { registre } from "@/lib/i18n/fr/registre";

export const metadata: Metadata = { title: registre.feed.title };

export default function Page() {
  return <OfficialFeed />;
}
