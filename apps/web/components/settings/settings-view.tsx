"use client";

import type { components } from "@fanilo/shared";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { Check, CircleMinus, LoaderCircle, RefreshCw, RotateCcw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

type Health = components["schemas"]["HealthOut"];
type ServiceCheck = components["schemas"]["Check"];

const timeFmt = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const STATE_ICON = { up: Check, down: TriangleAlert, not_configured: CircleMinus } as const;

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
          <h2 id="health-title" className="font-semibold">
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
          <RefreshCw className={cn(isValidating && "animate-spin")} aria-hidden />
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
      <h2 id="demo-title" className="font-semibold">
        {t.settings.demoTitle}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t.settings.demoLead}</p>
      <div className="mt-4">
        {confirming ? (
          <Button variant="destructive" className="h-10" onClick={reset} onBlur={() => setConfirming(false)} autoFocus>
            <RotateCcw aria-hidden />
            {t.settings.demoConfirm}
          </Button>
        ) : (
          <Button variant="outline" className="h-10" onClick={() => setConfirming(true)} disabled={pending}>
            {pending ? <LoaderCircle className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />}
            {t.settings.demoReset}
          </Button>
        )}
      </div>
    </section>
  );
}

export function SettingsView() {
  const { ws } = useParams<{ ws: string }>();
  const { role } = useWorkspace(ws);

  return (
    <div className="mx-auto max-w-4xl px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <header className="pb-6">
        <h1 className="text-[1.75rem] leading-tight font-semibold tracking-tight">{t.settings.title}</h1>
        <p className="mt-1 text-muted-foreground">{t.settings.lead}</p>
      </header>
      {/* Service health is for whoever runs the desk; journalists only need to know who to ask. */}
      {role === "admin" ? (
        <div className="space-y-8">
          <HealthSection />
          <DemoSection ws={ws} />
        </div>
      ) : (
        role && <p className="max-w-prose text-muted-foreground">{t.settings.adminOnly}</p>
      )}
    </div>
  );
}
