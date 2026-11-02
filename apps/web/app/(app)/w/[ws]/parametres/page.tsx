import type { Metadata } from "next";
import { SettingsView } from "@/components/settings/settings-view";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.settings.title };

export default function SettingsPage() {
  return <SettingsView />;
}
