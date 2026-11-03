"use client";

import { useParams, usePathname } from "next/navigation";
import { SECTIONS } from "@/components/shell/nav";
import { PillTabs } from "@/components/ui/pill-tabs";
import { t } from "@/lib/i18n/live";

/** The strip that ties the sections of one tab together (Annuaire: contacts, documents, registry,
 * figures; Dossiers: dossiers, sources), on the sliding pill of every tab row. */
export function SectionTabs({ group }: { group: keyof typeof SECTIONS }) {
  const { ws } = useParams<{ ws: string }>();
  const pathname = usePathname();
  const items = SECTIONS[group].map((s) => ({ value: s.path, label: s.label, href: `/w/${ws}/${s.path}` }));
  const current = items.find((s) => pathname === s.href || pathname.startsWith(`${s.href}/`))?.value ?? "";
  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-5 lg:px-8">
      <PillTabs kind="nav" className="seg-scroll" label={t.nav.sections} value={current} items={items} />
    </div>
  );
}
