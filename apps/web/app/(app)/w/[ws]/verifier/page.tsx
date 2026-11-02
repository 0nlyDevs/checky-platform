import type { Metadata } from "next";
import { AskView } from "@/components/ask/ask-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.ask.title };

export default function AskPage() {
  return <AskView />;
}
