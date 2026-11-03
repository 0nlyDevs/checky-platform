"use client";

import { useParams, useSearchParams } from "next/navigation";
import { SourcesPanel } from "@/components/sources/sources-panel";
import { t } from "@/lib/i18n/live";
import { PillTabs } from "@/components/ui/pill-tabs";

/** All sources, with recordings as a tab (they are sources too; the transcript lives on each one). */
export function SourcesView() {
  const { ws } = useParams<{ ws: string }>();
  const audio = useSearchParams().get("vue") === "enregistrements";
  const tabs = [
    { key: "all", label: t.sources.tabs.all, href: `/w/${ws}/sources`, active: !audio },
    { key: "audio", label: t.sources.tabs.audio, href: `/w/${ws}/sources?vue=enregistrements`, active: audio },
  ];
  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 *:max-w-4xl lg:px-8 lg:pt-8">
      <header className="pb-5">
        <h1 className="page-title">{t.sources.title}</h1>
        <p className="mt-1 max-w-prose text-muted-foreground">{audio ? t.transcriptions.lead : t.sources.lead}</p>
      </header>
      <PillTabs
        kind="nav"
        className="mb-5"
        label={t.sources.tabsLabel}
        value={audio ? "audio" : "all"}
        items={tabs.map((tab) => ({ value: tab.key, label: tab.label, href: tab.href }))}
      />
      {audio ? <SourcesPanel key="audio" ws={ws} kind="audio" /> : <SourcesPanel key="all" ws={ws} />}
    </div>
  );
}
