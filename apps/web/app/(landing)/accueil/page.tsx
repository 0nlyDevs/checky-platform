import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = {
  title: { absolute: `${brand.name} · ${t.site.metaTitle}` },
  description: t.site.metaDescription,
};

export default function HomePage() {
  return <Landing />;
}
