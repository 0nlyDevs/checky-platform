import type { Metadata } from "next";
import { TranscriptionsView } from "@/components/sources/transcriptions-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.transcriptions.title };

export default function TranscriptionsPage() {
  return <TranscriptionsView />;
}
