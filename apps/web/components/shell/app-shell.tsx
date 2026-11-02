"use client";

import type { Me } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import useSWR from "swr";
import { IconCaretUpDown, IconCheck, IconMagnifyingGlass, IconMonitor, IconMoon, IconPlus, IconSealCheck, IconSignOut, IconSun } from "@/lib/icons";
import { AssistantProvider } from "@/components/assistant/assistant-context";
import { Wordmark } from "@/components/brand/logo";
import { openPalette } from "@/components/shell/command-palette";
import { NAV, WORKSPACE_NAV } from "@/components/shell/nav";
import { EcoMenuItem, FontMenuRow } from "@/components/prefs/prefs-controls";
import { PreferenceDock } from "@/components/shell/preference-dock";
import { TabBar, TabIsland } from "@/components/shell/tab-island";
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
import { VerificationBanner } from "@/components/verification/status";
import { t } from "@/lib/i18n/fr";
import type { SessionUser } from "@/lib/session";
import { toggleThemeWithReveal } from "@/lib/theme-reveal";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

/** The workspace beside the wordmark: its name, and the menu to change it. */
function WorkspaceSwitcher({ me, current }: { me?: Me; current?: string }) {
  const active = me?.memberships.find((m) => m.workspace_id === current);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="bar-scope" aria-label={`${t.nav.workspace} : ${active?.name ?? "—"}`}>
        <span className="truncate">{active?.name ?? "—"}</span>
        <IconCaretUpDown className="size-4 shrink-0" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>{t.nav.workspace}</DropdownMenuLabel>
        {me?.memberships.map((m) => (
          <DropdownMenuItem key={m.workspace_id} asChild>
            <Link href={`/w/${m.workspace_id}/rubrique`}>
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

/** The avatar: who is signed in, the newsroom's pages (Équipe, Paramètres), the theme, sign out. */
function UserMenu({ user, ws, team, admin = false }: { user: SessionUser; ws?: string; team: boolean; admin?: boolean }) {
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
      <DropdownMenuTrigger className="bar-avatar" data-ripple aria-label={`${t.nav.account} : ${user.name}`}>
        {initials(user.name)}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="w-60">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate font-bold text-foreground">{user.name}</span>
          <span className="block truncate text-muted-foreground">{user.email}</span>
        </DropdownMenuLabel>
        {ws && team && (
          <>
            <DropdownMenuSeparator />
            {WORKSPACE_NAV.map(({ label, icon: Icon, path }) => (
              <DropdownMenuItem key={path} asChild>
                <Link href={`/w/${ws}/${path}`}>
                  <Icon className="size-4" aria-hidden /> {label}
                </Link>
              </DropdownMenuItem>
            ))}
          </>
        )}
        {admin && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/checky">
                <IconSealCheck className="size-4" aria-hidden /> {t.verification.review.menu}
              </Link>
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>{t.nav.theme}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={theme}
          onValueChange={(v) => (v === "light" || v === "dark" ? toggleThemeWithReveal(v, setTheme) : setTheme(v))}
        >
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
        <FontMenuRow />
        <EcoMenuItem />
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <IconSignOut className="size-4" aria-hidden /> {t.auth.signOut}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * The desk: no rail. A quiet top bar says where you are (wordmark and workspace, the ink tab island,
 * the avatar); the corners hold what you can do (preferences bottom-left, Checky bottom-right).
 * Under 640 px the tabs move to an ink bar at the thumb.
 */
export function AppShell({ user, children }: { user: SessionUser; children: React.ReactNode }) {
  const { ws } = useParams<{ ws?: string }>();
  const { data: me } = useSWR<Me>("/me", fetcher);

  // Le carnet's shelves follow the daily places; priority+ folds whatever does not fit.
  const items = NAV;
  return (
    <AssistantProvider scope="desk">
      <div data-app-shell className="min-h-dvh bg-background">
        <a
          href="#contenu"
          className="sr-only z-50 rounded-md bg-card px-3 py-2 font-bold text-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:ring-2 focus:ring-ring"
        >
          {t.nav.skip}
        </a>
        <header className="desk-bar" data-desk-bar>
          <div className="bar-brand">
            <Link href="/" className="bar-word">
              <Wordmark mark={false} />
            </Link>
            {ws && <WorkspaceSwitcher me={me} current={ws} />}
          </div>
          <TabIsland ws={ws} items={items} />
          <div className="bar-right">
            <button type="button" className="bar-icon" data-ripple onClick={openPalette} aria-label={t.nav.search} aria-keyshortcuts="Control+K">
              <IconMagnifyingGlass className="size-5" aria-hidden />
            </button>
            <UserMenu user={user} ws={ws} team admin={Boolean(me?.platform_admin)} />
          </div>
        </header>
        {ws && <VerificationBanner ws={ws} />}

        <main id="contenu" tabIndex={-1} className="desk-main outline-none">
          {children}
        </main>

        <PreferenceDock settingsHref={ws ? `/w/${ws}/parametres` : undefined} />
        <TabBar ws={ws} items={items} />
      </div>
    </AssistantProvider>
  );
}

export function ShellSkeleton() {
  return (
    <div data-app-shell className="min-h-dvh bg-background" aria-busy>
      <div className="desk-bar">
        <div className="bar-brand">
          <Wordmark mark={false} />
        </div>
        <div className="tab-wrap">
          <div className="tab-island h-12 w-[min(36rem,100%)]" />
        </div>
        <div className="bar-right">
          <span className="bar-avatar" />
        </div>
      </div>
      <div className="desk-main space-y-6 pt-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    </div>
  );
}
