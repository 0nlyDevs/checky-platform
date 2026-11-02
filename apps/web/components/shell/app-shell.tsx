"use client";

import type { Me } from "@fanilo/shared";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import useSWR from "swr";
import { Check, ChevronsUpDown, LogOut, Monitor, Moon, Plus, Sun } from "lucide-react";
import { Wordmark } from "@/components/brand/logo";
import { NAV } from "@/components/shell/nav";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { clearApiToken, fetcher } from "@/lib/api";
import { authClient } from "@/lib/auth-client";
import { t } from "@/lib/i18n/fr";
import type { SessionUser } from "@/lib/session";
import { cn } from "@/lib/utils";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

function WorkspaceSwitcher({ me, current }: { me?: Me; current?: string }) {
  const active = me?.memberships.find((m) => m.workspace_id === current);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left outline-none hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-sidebar-ring">
        <span className="min-w-0 flex-1">
          <span className="block text-xs text-sidebar-muted">{t.nav.workspace}</span>
          <span className="block truncate font-medium">{active?.name ?? "—"}</span>
        </span>
        <ChevronsUpDown className="size-4 shrink-0 text-sidebar-muted" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>{t.nav.workspace}</DropdownMenuLabel>
        {me?.memberships.map((m) => (
          <DropdownMenuItem key={m.workspace_id} asChild>
            <Link href={`/w/${m.workspace_id}/affirmations`}>
              <span className="flex-1 truncate">{m.name}</span>
              {m.workspace_id === current && <Check className="size-4" aria-hidden />}
            </Link>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/?nouveau=1">
            <Plus className="size-4" aria-hidden />
            {t.nav.newWorkspace}
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu({ user, compact = false }: { user: SessionUser; compact?: boolean }) {
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  async function signOut() {
    clearApiToken();
    await authClient.signOut();
    router.replace("/connexion");
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex items-center gap-2.5 rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
          compact ? "p-1" : "w-full px-2.5 py-2 hover:bg-sidebar-accent",
        )}
        aria-label={user.name}
      >
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-sidebar-accent font-display text-sm font-semibold text-sidebar-accent-foreground ring-1 ring-sidebar-foreground/30">
          {initials(user.name)}
        </span>
        {!compact && (
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{user.name}</span>
            <span className="block truncate text-xs text-sidebar-muted">{user.email}</span>
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={compact ? "end" : "start"} side={compact ? "bottom" : "top"} className="w-56">
        <DropdownMenuLabel>{t.nav.theme}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <Sun className="size-4" aria-hidden /> {t.nav.themeLight}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon className="size-4" aria-hidden /> {t.nav.themeDark}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor className="size-4" aria-hidden /> {t.nav.themeSystem}
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut className="size-4" aria-hidden /> {t.auth.signOut}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function NavLinks({ ws, variant }: { ws?: string; variant: "rail" | "bar" }) {
  const pathname = usePathname();
  const items = variant === "bar" ? NAV.slice(0, 4) : NAV;
  return (
    <ul className={variant === "rail" ? "space-y-0.5" : "grid grid-cols-4"}>
      {items.map(({ label, icon: Icon, path }) => {
        const href = ws && path ? `/w/${ws}/${path}` : undefined;
        const active = href ? pathname.startsWith(href) : false;
        const base =
          variant === "rail"
            ? "flex items-center gap-3 rounded-md px-2.5 py-2 text-[0.9375rem]"
            : "flex flex-col items-center gap-1 px-1 pt-2 pb-1.5 text-xs";
        if (!href) {
          const reason = path ? t.nav.needsWorkspace : t.nav.comingSoon;
          return (
            <li key={label}>
              <span aria-disabled className={cn(base, "cursor-default text-sidebar-muted/70")} title={reason}>
                <Icon className="size-[1.125rem] shrink-0" aria-hidden />
                <span className="truncate">{label}</span>
                {variant === "rail" && !path && (
                  <span className="ml-auto text-[0.6875rem] uppercase tracking-wider">{t.nav.comingSoon}</span>
                )}
              </span>
            </li>
          );
        }
        return (
          <li key={label}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                base,
                "outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                active
                  ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/60",
                variant === "bar" && active && "bg-transparent shadow-[inset_0_2px_0_0_var(--sidebar-foreground)]",
              )}
            >
              <Icon className="size-[1.125rem] shrink-0" aria-hidden />
              <span className="truncate">{label}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function AppShell({ user, children }: { user: SessionUser; children: React.ReactNode }) {
  const { ws } = useParams<{ ws?: string }>();
  const { data: me } = useSWR<Me>("/me", fetcher);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col bg-sidebar p-3 text-sidebar-foreground lg:flex">
        <Link href="/" className="px-2.5 pt-2 pb-5 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
          <Wordmark />
        </Link>
        <WorkspaceSwitcher me={me} current={ws} />
        <nav aria-label="Navigation principale" className="mt-4 flex-1">
          <NavLinks ws={ws} variant="rail" />
        </nav>
        <div className="border-t border-sidebar-border pt-3">
          <UserMenu user={user} />
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex items-center gap-3 bg-sidebar px-4 py-2.5 text-sidebar-foreground lg:hidden">
        <Wordmark className="shrink-0" />
        <div className="min-w-0 flex-1">
          <WorkspaceSwitcher me={me} current={ws} />
        </div>
        <UserMenu user={user} compact />
      </header>

      <div className="min-w-0 pb-20 lg:pb-0">{children}</div>

      <nav
        aria-label="Navigation principale"
        className="fixed inset-x-0 bottom-0 z-30 bg-sidebar text-sidebar-foreground pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        <NavLinks ws={ws} variant="bar" />
      </nav>
    </div>
  );
}

export function ShellSkeleton() {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]" aria-busy>
      <aside className="hidden h-dvh flex-col gap-4 bg-sidebar p-5 lg:flex">
        <Wordmark className="text-sidebar-foreground" />
        <div className="h-12 rounded-md bg-sidebar-accent/60" />
        <div className="space-y-2">
          {NAV.map((n) => (
            <div key={n.label} className="h-8 rounded-md bg-sidebar-accent/40" />
          ))}
        </div>
      </aside>
      <div className="h-14 bg-sidebar lg:hidden" />
      <div className="space-y-6 p-5 lg:p-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    </div>
  );
}
