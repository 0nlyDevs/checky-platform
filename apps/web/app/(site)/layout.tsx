import { anton, specialElite } from "@/app/fonts/site";

// Public pages are a case file (the dossier world); the app keeps its programme grid.
export default function SiteLayout({ children }: LayoutProps<"/">) {
  return <div className={`site ${anton.variable} ${specialElite.variable} min-h-dvh`}>{children}</div>;
}
