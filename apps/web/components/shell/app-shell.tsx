"use client";

import type { Me } from "@checky/shared";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import useSWR from "swr";
import { IconCaretUpDown, IconCheck, IconMagnifyingGlass, IconMonitor, IconMoon, IconNewspaper, IconPlus, IconSealCheck, IconShieldCheck, IconSignOut, IconSun } from "@/lib/icons";
import { AssistantProvider } from "@/components/assistant/assistant-context";
import { Wordmark } from "@/components/brand/logo";
import { openPalette } from "@/components/shell/command-palette";
import { NAV, WORKSPACE_NAV } from "@/components/shell/nav";
import { EcoMenuItem, FontMenuRow, LanguageMenuRow } from "@/components/prefs/prefs-controls";
import { PreferenceDock } from "@/components/shell/preference-dock";
import { OfflineBanner, OfflineWarmup } from "@/components/pwa/offline-banner";
import { clearPrivateCache } from "@/components/pwa/service-worker";
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
import { t } from "@/lib/i18n/live";
import type { SessionUser } from "@/lib/session";
import { toggleThemeWithReveal } from "@/lib/theme-reveal";

const subscribeNothing = () => () => {};
/** True on Apple systems, where the palette's shortcut reads ⌘ K (false on the server). */
function useApple() {
  return useSyncExternalStore(subscribeNothing, () => /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent), () => false);
}

/** Search everywhere, with the key that opens it from anywhere (Ctrl K, ⌘ K on a Mac). */
function SearchButton() {
  const apple = useApple();
  return (
    <button
      type="button"
      className="bar-icon bar-search"
      data-ripple
      onClick={openPalette}
      aria-label={t.nav.search}
      aria-keyshortcuts={apple ? "Meta+K" : "Control+K"}
    >
      <IconMagnifyingGlass className="size-5" aria-hidden />
      <kbd className="bar-kbd" aria-hidden>
        {apple ? "⌘" : "Ctrl"} K
      </kbd>
    </button>
  );
}

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
      <DropdownMenuTrigger className="bar-scope" aria-label={`${t.nav.workspace}${t.common.colon} ${active?.name ?? "—"}`}>
        <span className="truncate">{active?.name ?? "—"}</span>
        <IconCaretUpDown className="size-4 shrink-0" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>{t.nav.workspace}</DropdownMenuLabel>
        {me?.memberships.map((m) => (
          <DropdownMenuItem key={m.workspace_id} asChild>
            <Link href={`/w/${m.workspace_id}/beat`}>
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
// What this account is: one of its newsroom's journalists, or the Checky team that reviews newsrooms.
function AccountKind({ admin }: { admin: boolean }) {
  const Icon = admin ? IconShieldCheck : IconNewspaper;
  return (
    <span
      className={`mt-2 inline-flex items-center gap-1.5 rounded-[6px] border px-2 py-0.5 text-xs font-bold ${
        admin ? "border-tag-inverted bg-tag-inverted text-tag-inverted-foreground" : "border-border text-foreground"
      }`}
    >
      <Icon className="size-3.5" aria-hidden /> {admin ? t.nav.roleAdmin : t.nav.roleJournalist}
    </span>
  );
}

function UserMenu({ user, ws, team, admin = false }: { user: SessionUser; ws?: string; team: boolean; admin?: boolean }) {
  const { theme, setTheme } = useTheme();

  async function signOut() {
    clearApiToken();
    await clearPrivateCache();
    await authClient.signOut();
    // A full page load drops everything the account left in memory (SWR's /me and newsrooms).
    window.location.replace("/sign-in");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="bar-avatar" data-ripple aria-label={`${t.nav.account}${t.common.colon} ${user.name}, ${admin ? t.nav.roleAdmin : t.nav.roleJournalist}`}>
        {initials(user.name)}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="w-60">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate font-bold text-foreground">{user.name}</span>
          <span className="block truncate text-muted-foreground">{user.email}</span>
          <AccountKind admin={admin} />
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
        <LanguageMenuRow />
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
            <SearchButton />
            <UserMenu user={user} ws={ws} team admin={Boolean(me?.platform_admin)} />
          </div>
        </header>
        <OfflineBanner scope="desk" />
        {ws && <OfflineWarmup ws={ws} />}
        {ws && <VerificationBanner ws={ws} />}

        <main id="contenu" tabIndex={-1} className="desk-main outline-none">
          {children}
        </main>

        <PreferenceDock settingsHref={ws ? `/w/${ws}/settings` : undefined} />
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
