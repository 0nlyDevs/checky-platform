"use client";
import { AskView } from "@/components/ask/ask-view";
import { resources as t } from "@/lib/i18n/fr/resources";
export function AnglesView() {
  return <main className="mx-auto max-w-4xl px-4 py-8 lg:px-8"><h1 className="page-title">{t.angles}</h1><p className="my-4 max-w-prose text-lg text-muted-foreground">{t.anglesLead}</p><AskView embedded initialQuestion={t.anglePrompt} /></main>;
}
