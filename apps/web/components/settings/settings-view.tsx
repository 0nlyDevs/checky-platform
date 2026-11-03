"use client";

import type { components } from "@checky/shared";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { IconArrowCounterClockwise, IconArrowsClockwise, IconCheck, IconCircleNotch, IconMinusCircle, IconWarning } from "@/lib/icons";
import { toast } from "sonner";
import { undoable } from "@/lib/undo";
import { NewsroomRules } from "@/components/claims/publication-panel";
import { BeatsSection, OfficialSourcesSection, PlaceSection } from "@/components/settings/newsroom-sections";
import { RadiosSection } from "@/components/settings/radios-section";
import { SmsSimulator } from "@/components/settings/sms-simulator";
import { MembersView } from "@/components/members/members-view";
import { VerificationSection } from "@/components/verification/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

type Health = components["schemas"]["HealthOut"];
type ServiceCheck = components["schemas"]["Check"];

const timeFmt = dateFormat({ hour: "2-digit", minute: "2-digit", second: "2-digit" });

const STATE_ICON = { up: IconCheck, down: IconWarning, not_configured: IconMinusCircle } as const;

function hint(key: string, kind: "core" | "ai") {
  if (kind === "ai") return t.settings.notConfiguredHint.ai(key);
  return key === "storage" ? t.settings.notConfiguredHint.storage : null;
}

function ServiceRow({ name, check, kind }: { name: string; check: ServiceCheck; kind: "core" | "ai" }) {
  const Icon = STATE_ICON[check.status];
  const down = check.status === "down";
  const off = check.status === "not_configured";
  const note = down ? check.detail : off ? hint(name, kind) : check.model;
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
      {/* Phones put latency and state on their own line so hints stay readable in full. */}
      <div className="w-full min-w-0 sm:w-auto sm:flex-1">
        <p className={cn("font-medium", off && "text-muted-foreground")}>{t.settings.services[name] ?? name}</p>
        {note && <p className="text-sm break-words text-muted-foreground">{note}</p>}
      </div>
      {check.latency_ms != null && !down && (
        <span className="font-display text-sm tracking-wide tabular text-muted-foreground">
          {t.settings.latency(check.latency_ms)}
        </span>
      )}
      {/* Down is an error, so it borrows the "faux" soft/ink pair like form errors; up and off stay in ink. */}
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-sm py-0.5 text-sm",
          down ? "bg-verdict-false-soft px-2 font-medium text-verdict-false-ink" : off ? "text-muted-foreground" : "text-foreground",
        )}
      >
        <Icon className="size-4 shrink-0" aria-hidden />
        {t.settings.state[check.status]}
      </span>
    </li>
  );
}

function ServiceGroup({ title, checks, kind }: { title: string; checks: Record<string, ServiceCheck>; kind: "core" | "ai" }) {
  return (
    <div>
      <h3 className="pb-2 text-sm text-muted-foreground">{title}</h3>
      <ul className="divide-y divide-border rounded-lg border border-border bg-card">
        {Object.entries(checks).map(([name, check]) => (
          <ServiceRow key={name} name={name} check={check} kind={kind} />
        ))}
      </ul>
    </div>
  );
}

function HealthSection() {
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const { data, error, isValidating, mutate } = useSWR<Health>("/health", fetcher, {
    revalidateOnFocus: false,
    onSuccess: () => setCheckedAt(new Date()),
  });
  const all = data ? [...Object.values(data.checks), ...Object.values(data.ai)] : [];
  const down = all.filter((c) => c.status === "down").length;

  return (
    <section aria-labelledby="health-title" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="health-title" className="font-display text-lg font-bold">
            {t.settings.healthTitle}
          </h2>
          {data && (
            <p className="mt-0.5 text-sm text-muted-foreground" role="status">
              {down ? t.settings.someDown(down) : t.settings.allUp}
              {checkedAt && (
                <span className="font-display tracking-wide tabular"> · {t.settings.checkedAt(timeFmt.format(checkedAt))}</span>
              )}
            </p>
          )}
        </div>
        <Button variant="outline" className="h-9" onClick={() => mutate()} disabled={isValidating}>
          <IconArrowsClockwise className={cn(isValidating && "animate-spin")} aria-hidden />
          {t.settings.refresh}
        </Button>
      </div>

      {error ? (
        <p className="rounded-md bg-verdict-false-soft px-3 py-2 text-sm text-verdict-false-ink" role="alert">
          {t.settings.healthError}
        </p>
      ) : !data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="space-y-5">
          <ServiceGroup title={t.settings.groups.core} checks={data.checks} kind="core" />
          <ServiceGroup title={t.settings.groups.ai} checks={data.ai} kind="ai" />
        </div>
      )}
    </section>
  );
}

function PublicSection({ ws }: { ws: string }) {
  const { data, mutate } = useSWR<{ is_public: boolean }>(`/workspaces/${ws}`, fetcher);
  const [pending, setPending] = useState(false);

  async function toggle(on: boolean, undo = true) {
    setPending(true);
    try {
      await mutate(api<{ is_public: boolean }>(`/workspaces/${ws}`, { method: "PATCH", body: JSON.stringify({ is_public: on }) }), { revalidate: false });
      if (undo) undoable(t.settings.publicSaved(on), () => toggle(!on, false));
      else toast.success(t.settings.publicSaved(on));
    } catch {
      toast.error(t.settings.publicFailed);
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="public-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="public-title" className="font-display text-lg font-bold">
        {t.settings.publicTitle}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t.settings.publicLead}</p>
      <label className="mt-4 flex items-center gap-3 text-sm font-medium">
        <input
          type="checkbox"
          className="size-5 accent-primary"
          checked={data?.is_public ?? false}
          disabled={!data || pending}
          onChange={(e) => toggle(e.target.checked)}
        />
        {t.settings.publicOn}
      </label>
      {data?.is_public && (
        <a href="/verdicts" target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm underline underline-offset-4">
          {t.settings.publicLink}
        </a>
      )}
    </section>
  );
}

function DemoSection({ ws }: { ws: string }) {
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);

  async function reset() {
    setConfirming(false);
    setPending(true);
    try {
      const res = await api<{ items: number }>(`/workspaces/${ws}/demo/reset`, { method: "POST" });
      toast.success(t.settings.demoDone(res.items));
    } catch {
      toast.error(t.settings.demoFailed);
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="demo-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="demo-title" className="font-display text-lg font-bold">
        {t.settings.demoTitle}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t.settings.demoLead}</p>
      <div className="mt-4">
        {confirming ? (
          <Button variant="destructive" className="h-10" onClick={reset} onBlur={() => setConfirming(false)} autoFocus>
            <IconArrowCounterClockwise aria-hidden />
            {t.settings.demoConfirm}
          </Button>
        ) : (
          <Button variant="outline" className="h-10" onClick={() => setConfirming(true)} disabled={pending}>
            {pending ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconArrowCounterClockwise aria-hidden />}
            {t.settings.demoReset}
          </Button>
        )}
      </div>
    </section>
  );
}

const INDEX = [
  { id: "verification", get label() { return t.settings.index.verification; } },
  { id: "equipe", get label() { return t.settings.index.team; } },
  { id: "regles", get label() { return t.settings.index.rules; } },
  { id: "rubriques", get label() { return t.settings.index.beats; } },
  { id: "lieu", get label() { return t.settings.index.place; } },
  { id: "sources-officielles", get label() { return t.settings.index.official; } },
  { id: "publication", get label() { return t.settings.index.public; } },
  { id: "sms", get label() { return t.settings.index.sms; } },
  { id: "radios", get label() { return t.settings.index.radios; } },
  { id: "services", get label() { return t.settings.index.health; } },
  { id: "demo", get label() { return t.settings.index.demo; } },
] as const;

/** The page's index, beside the sections from lg up: where am I, and one click to the rest. */
function SettingsIndex() {
  const [current, setCurrent] = useState<string>(INDEX[0].id);
  useEffect(() => {
    // Measured on scroll rather than observed: the sections load at different times and move.
    let frame = 0;
    const pick = () => {
      frame = 0;
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      const line = window.innerHeight * 0.3;
      let at: string = INDEX[0].id;
      for (const x of INDEX) {
        const node = document.getElementById(x.id);
        if (node && (atBottom || node.getBoundingClientRect().top <= line)) at = x.id;
      }
      setCurrent(at);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(pick);
    };
    pick();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    // Sections that finish loading push the others down without any scroll.
    const grown = new ResizeObserver(onScroll);
    grown.observe(document.body);
    return () => {
      cancelAnimationFrame(frame);
      grown.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);
  return (
    <nav aria-label={t.settings.index.label} className="sticky top-24 hidden self-start lg:block">
      <ul className="space-y-0.5 border-l border-border">
        {INDEX.map((x) => (
          <li key={x.id}>
            <a
              href={`#${x.id}`}
              aria-current={current === x.id ? "true" : undefined}
              className={cn(
                "-ml-px block border-l-2 py-1.5 pl-4 text-sm transition-colors",
                current === x.id ? "border-foreground font-bold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {x.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A section of the page the index can point at. */
function Anchor({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <div id={id} className="scroll-mt-24">
      {children}
    </div>
  );
}

export function SettingsView() {
  const { ws } = useParams<{ ws: string }>();
  const { joined } = useWorkspace(ws);

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <header className="max-w-4xl pb-6">
        <h1 className="page-title">{t.settings.title}</h1>
        <p className="mt-1 text-muted-foreground">{t.team.settings.lead}</p>
      </header>
      {joined && (
        <div className="lg:grid lg:grid-cols-[12rem_minmax(0,56rem)] lg:gap-12">
          <SettingsIndex />
          <div className="min-w-0 space-y-10">
            {/* The newsroom's own rules first; then what the public asks and where verdicts go back out;
                service health and the demo last. Every journalist of the newsroom sets them. */}
            <VerificationSection ws={ws} />
            <MembersView embedded />
            <Anchor id="regles">
              <NewsroomRules ws={ws} />
            </Anchor>
            <Anchor id="rubriques">
              <BeatsSection ws={ws} />
            </Anchor>
            <Anchor id="lieu">
              <PlaceSection ws={ws} />
            </Anchor>
            <Anchor id="sources-officielles">
              <OfficialSourcesSection ws={ws} />
            </Anchor>
            <Anchor id="publication">
              <PublicSection ws={ws} />
            </Anchor>
            <Anchor id="sms">
              <SmsSimulator ws={ws} />
            </Anchor>
            <Anchor id="radios">
              <RadiosSection ws={ws} canEdit />
            </Anchor>
            <Anchor id="services">
              <HealthSection />
            </Anchor>
            <Anchor id="demo">
              <DemoSection ws={ws} />
            </Anchor>
          </div>
        </div>
      )}
    </div>
  );
}
