"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { SECTIONS } from "@/components/shell/nav";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

/** The strip that ties the sections of one tab together (Annuaire: contacts, documents, registry,
 * figures; Dossiers: dossiers, sources). */
export function SectionTabs({ group }: { group: keyof typeof SECTIONS }) {
  const { ws } = useParams<{ ws: string }>();
  const pathname = usePathname();
  return (
    <nav aria-label={t.nav.sections} className="mx-auto max-w-[90rem] px-4 pt-5 lg:px-8">
      <div className="flex gap-1 overflow-x-auto border-b border-border">
        {SECTIONS[group].map((s) => {
          const href = `/w/${ws}/${s.path}`;
          const current = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={s.path}
              href={href as never}
              aria-current={current ? "page" : undefined}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors duration-150",
                current ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {s.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
