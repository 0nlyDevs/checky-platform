import { anton, specialElite } from "@/app/fonts/site";
import { AssistantWidget } from "@/components/assistant/assistant-widget";

// Public pages are a case file (the dossier world); the app keeps its programme grid.
export default function SiteLayout({ children }: LayoutProps<"/">) {
  return (
    <div className={`site ${anton.variable} ${specialElite.variable} min-h-dvh`}>
      {children}
      <AssistantWidget />
    </div>
  );
}
