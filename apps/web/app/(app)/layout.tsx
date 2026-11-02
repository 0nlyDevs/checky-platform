import { Suspense } from "react";
import { CommandPalette } from "@/components/shell/command-palette";
import { AppShell, ShellSkeleton } from "@/components/shell/app-shell";
import { Shortcuts } from "@/components/shell/shortcuts";
import { getCurrentUser } from "@/lib/session";

async function SessionShell({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  return (
    <AppShell user={user}>
      {children}
      {/* inside the shell's providers; both are portals or render nothing */}
      <CommandPalette />
      <Shortcuts />
    </AppShell>
  );
}

export default function AppLayout({ children }: LayoutProps<"/">) {
  // The session read streams in behind the boundary; the skeleton is the static shell.
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <SessionShell>{children}</SessionShell>
    </Suspense>
  );
}
