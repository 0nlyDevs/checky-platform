import type { Metadata } from "next";
import { Suspense } from "react";
import { SectionTabs } from "@/components/shell/section-tabs";
import { AnnuaireView } from "@/components/annuaire/annuaire-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.dossier.annuaire.title };

export default function Page() {
  return (
    <Suspense>
      <SectionTabs group="annuaire" />
      <AnnuaireView />
    </Suspense>
  );
}
