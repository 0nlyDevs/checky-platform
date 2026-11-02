"use client";

import type { Me } from "@fanilo/shared";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import useSWR from "swr";
import { IconCaretUpDown, IconCheck, IconMonitor, IconMoon, IconPlus, IconSignOut, IconSun } from "@/lib/icons";
import { AssistantLauncher, AssistantProvider } from "@/components/assistant/assistant-context";
import { Wordmark } from "@/components/brand/logo";
import { BAR_NAV, CARNET_NAV, NAV, WORKSPACE_NAV, type NavItem } from "@/components/shell/nav";
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
          <span className="block truncate font-bold">{active?.name ?? "—"}</span>
        </span>
        <IconCaretUpDown className="size-4 shrink-0 text-sidebar-muted" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>{t.nav.workspace}</DropdownMenuLabel>
        {me?.memberships.map((m) => (
          <DropdownMenuItem key={m.workspace_id} asChild>
            <Link href={`/w/${m.workspace_id}/${m.role === "issuer" ? "registre" : m.role === "veilleur" ? "veille" : "rubrique"}`}>
              <span className="flex-1 truncate">{m.name}</span>
              {m.workspace_id === current && <IconCheck className="size-4" aria-hidden />}
            </Link>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/?nouveau=1">
            <IconPlus className="size-4" aria-hidden />
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
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-foreground font-display text-sm font-bold text-background">
          {initials(user.name)}
        </span>
        {!compact && (
          <span className="min-w-0">
            <span className="block truncate text-sm font-bold">{user.name}</span>
            <span className="block truncate text-xs text-sidebar-muted">{user.email}</span>
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={compact ? "end" : "start"} side={compact ? "bottom" : "top"} className="w-56">
        <DropdownMenuLabel>{t.nav.theme}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <IconSun className="size-4" aria-hidden /> {t.nav.themeLight}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <IconMoon className="size-4" aria-hidden /> {t.nav.themeDark}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <IconMonitor className="size-4" aria-hidden /> {t.nav.themeSystem}
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <IconSignOut className="size-4" aria-hidden /> {t.auth.signOut}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Rail and phone bar share the items; the active one carries the citron, the others stay ink. */
function NavLinks({ ws, variant, items = NAV }: { ws?: string; variant: "rail" | "bar"; items?: NavItem[] }) {
  const pathname = usePathname();
  const links = items.map(({ label: full, short, icon: Icon, path }) => {
        const label = variant === "bar" && short ? short : full;
        const href = ws && path ? `/w/${ws}/${path}` : undefined;
        // Analyser lives inside Vérifier now: its old address still lights Vérifier.
        const active = href ? pathname.startsWith(href) || (path === "verifier" && pathname.startsWith(`/w/${ws}/analyser`)) : false;
        if (!href) {
          return (
            <li key={label}>
              <span aria-disabled title={t.nav.needsWorkspace} className="flex cursor-default items-center gap-3 rounded-md px-3 py-2.5 text-sidebar-muted">
                <Icon className="size-5 shrink-0" aria-hidden />
                <span className="truncate">{label}</span>
              </span>
            </li>
          );
        }
        if (variant === "bar") {
          return (
            <li key={label}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className="flex flex-col items-center gap-1 px-1 pt-2 pb-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
              >
                <span className={cn("grid h-6 w-12 place-items-center rounded-full", active && "bg-sidebar-primary text-sidebar-primary-foreground")}>
                  <Icon className="size-[1.125rem]" aria-hidden />
                </span>
                <span className={cn(active && "font-bold")}>{label}</span>
              </Link>
            </li>
          );
        }
        return (
          <li key={label}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2.5 outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                active
                  ? "bg-sidebar-primary font-bold text-sidebar-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent",
              )}
            >
              <Icon className="size-5 shrink-0" aria-hidden />
              <span className="truncate">{label}</span>
            </Link>
          </li>
        );
      });
  // the phone bar's items sit in its own list, beside the assistant
  return variant === "rail" ? <ul className="space-y-1">{links}</ul> : <>{links}</>;
}

export function AppShell({ user, children }: { user: SessionUser; children: React.ReactNode }) {
  const { ws } = useParams<{ ws?: string }>();
  const { data: me } = useSWR<Me>("/me", fetcher);

  const role = me?.memberships.find(m => m.workspace_id === ws)?.role;
  const restricted = role === "issuer" || role === "veilleur";
  const allowedNav = restricted ? NAV.filter(n => n.path === (role === "issuer" ? "registre" : "veille")) : NAV;
  return (
    <AssistantProvider scope="desk">
      <div data-app-shell className="min-h-dvh bg-background lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
        <a
          href="#contenu"
          className="sr-only z-50 rounded-md bg-card px-3 py-2 font-bold text-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:ring-2 focus:ring-ring"
        >
          {t.nav.skip}
        </a>
        <aside className="sticky top-0 hidden h-dvh flex-col border-r border-sidebar-border bg-sidebar p-3 text-sidebar-foreground lg:flex">
          <Link href="/" className="rounded-md px-3 pt-2 pb-5 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
            <Wordmark />
          </Link>
          <WorkspaceSwitcher me={me} current={ws} />
          <nav aria-label="Navigation principale" className="mt-4 flex-1">
            <NavLinks ws={ws} variant="rail" items={allowedNav} />
            {ws && !restricted && (
              <>
                <p className="mt-4 mb-1 px-3 font-display text-[0.6875rem] font-bold tracking-[0.14em] text-sidebar-muted uppercase">
                  {t.nav.carnet}
                </p>
                <NavLinks ws={ws} variant="rail" items={CARNET_NAV} />
              </>
            )}
          </nav>
          {ws && !restricted && (
            <nav aria-label={t.nav.workspace} className="pb-3">
              <NavLinks ws={ws} variant="rail" items={WORKSPACE_NAV} />
            </nav>
          )}
          <AssistantLauncher variant="rail" />
          <div className="mt-3 border-t border-sidebar-border pt-3">
            <UserMenu user={user} />
          </div>
        </aside>

        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-sidebar-border bg-sidebar px-4 py-2 text-sidebar-foreground lg:hidden">
          <Link href="/" className="shrink-0 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
            <Wordmark />
          </Link>
          <div className="min-w-0 flex-1">
            <WorkspaceSwitcher me={me} current={ws} />
          </div>
          <UserMenu user={user} compact />
        </header>

        <main id="contenu" tabIndex={-1} className="min-w-0 pb-24 outline-none lg:pb-0">
          {children}
        </main>

        <nav
          aria-label="Navigation principale"
          className="fixed inset-x-0 bottom-0 z-30 border-t border-sidebar-border bg-sidebar pb-[env(safe-area-inset-bottom)] text-sidebar-foreground lg:hidden"
        >
          <ul className="grid grid-cols-5">
            <NavLinks ws={ws} variant="bar" items={restricted ? allowedNav : BAR_NAV} />
            <li>
              <AssistantLauncher variant="bar" />
            </li>
          </ul>
        </nav>
      </div>
    </AssistantProvider>
  );
}

export function ShellSkeleton() {
  return (
    <div data-app-shell className="min-h-dvh bg-background lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]" aria-busy>
      <aside className="hidden h-dvh flex-col gap-4 border-r border-sidebar-border bg-sidebar p-5 lg:flex">
        <Wordmark />
        <div className="h-12 rounded-md bg-sidebar-accent" />
        <div className="space-y-2">
          {NAV.map((n) => (
            <div key={n.label} className="h-10 rounded-md bg-sidebar-accent/70" />
          ))}
        </div>
      </aside>
      <div className="h-14 border-b border-sidebar-border bg-sidebar lg:hidden" />
      <div className="space-y-6 p-5 lg:p-10">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    </div>
  );
}
