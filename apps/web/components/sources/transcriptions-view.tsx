"use client";

import { useParams } from "next/navigation";
import { SourcesPanel } from "@/components/sources/sources-panel";
import { t } from "@/lib/i18n/fr";

export function TranscriptionsView() {
  const { ws } = useParams<{ ws: string }>();
  return (
    <div className="mx-auto max-w-4xl px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <header className="pb-6">
        <h1 className="text-[1.75rem] leading-tight font-semibold tracking-tight">{t.transcriptions.title}</h1>
        <p className="mt-1 max-w-prose text-muted-foreground">{t.transcriptions.lead}</p>
      </header>
      <SourcesPanel ws={ws} kind="audio" />
    </div>
  );
}
