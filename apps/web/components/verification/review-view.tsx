"use client";

import type { components, Me } from "@checky/shared";
import { useState } from "react";
import { toast } from "sonner";
import { notFound } from "next/navigation";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconArrowSquareOut, IconCheck, IconCircleNotch, IconPhone, IconX } from "@/lib/icons";
import { relative } from "@/lib/when";
import { PillTabs } from "@/components/ui/pill-tabs";

type Row = components["schemas"]["AdminRequestOut"];
const r = t.verification.review;
const TABS = ["pending", "approved", "refused"] as const;

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-medium break-words">{children}</dd>
    </div>
  );
}

function RequestCard({ row, onDone }: { row: Row; onDone: () => void }) {
  const q = row.request;
  const f = t.verification.form;
  const [busy, setBusy] = useState<null | "approve" | "refuse">(null);
  const [refusing, setRefusing] = useState(false);
  const [reason, setReason] = useState("");

  async function act(kind: "approve" | "refuse") {
    setBusy(kind);
    try {
      await api(`/platform/requests/${row.workspace_id}/${kind}`, {
        method: "POST",
        body: kind === "refuse" ? JSON.stringify({ reason: reason.trim() }) : undefined,
      });
      toast.success(kind === "approve" ? r.approved(row.newsroom) : r.refused(row.newsroom));
      setRefusing(false);
      onDone();
    } catch {
      toast.error(r.failed);
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="rounded-lg border border-border bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-bold">{q.outlet}</h2>
        <span className="text-sm text-muted-foreground">
          {t.verification.kinds[q.kind]} · {q.city}
          {q.region ? `, ${q.region}` : ""} · {q.country_name}
        </span>
      </div>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {row.newsroom} · {r.members(row.members)} · {r.sent(relative(row.submitted_at, new Date()))}
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <Fact label={f.fullName}>{q.full_name}</Fact>
        <Fact label={f.jobTitle}>{q.job_title}</Fact>
        <Fact label={f.phone}>
          <span className="tabular">{q.phone}</span>
        </Fact>
        <Fact label={f.email}>{q.email}</Fact>
        {q.press_card && <Fact label={r.pressCard}>{q.press_card}</Fact>}
        {row.reason && <Fact label={r.lastReason}>{row.reason}</Fact>}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button asChild variant="outline" size="lg">
          <a href={q.website} target="_blank" rel="noopener noreferrer nofollow">
            <IconArrowSquareOut aria-hidden />
            {r.officialPage}
          </a>
        </Button>
        <Button asChild variant="outline" size="lg">
          <a href={`tel:${q.phone}`}>
            <IconPhone aria-hidden />
            {r.call}
          </a>
        </Button>
        {row.status !== "approved" && (
          <Button size="lg" onClick={() => act("approve")} disabled={busy !== null}>
            {busy === "approve" ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconCheck aria-hidden />}
            {r.approve}
          </Button>
        )}
        {row.status === "pending" && !refusing && (
          <Button variant="ghost" size="lg" onClick={() => setRefusing(true)}>
            <IconX aria-hidden />
            {r.refuse}
          </Button>
        )}
      </div>
      {refusing && (
        <form
          className="mt-4 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void act("refuse");
          }}
        >
          <label htmlFor={`reason-${row.workspace_id}`} className="text-sm font-bold">
            {r.reason}
          </label>
          <textarea
            id={`reason-${row.workspace_id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            minLength={3}
            maxLength={1000}
            rows={2}
            className="w-full rounded-md border border-input bg-background px-3 py-2 outline-none focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
          />
          <div className="flex gap-2">
            <Button type="submit" variant="outline" size="lg" disabled={busy !== null || reason.trim().length < 3}>
              {busy === "refuse" && <IconCircleNotch className="animate-spin" aria-hidden />}
              {r.confirmRefuse}
            </Button>
            <Button type="button" variant="ghost" size="lg" onClick={() => setRefusing(false)}>
              {r.cancel}
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

/** The Checky team's page: newsroom requests, called back on the official page's number. */
export function ReviewView() {
  const { data: me } = useSWR<Me>("/me", fetcher);
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const rows = useSWR<Row[]>(me?.platform_admin ? `/platform/requests?status=${tab}` : null, fetcher);

  // Only the Checky team reviews requests: anyone else gets the page's 404, not an empty queue.
  if (me && !me.platform_admin) {
    notFound();
  }
  return (
    <div className="mx-auto max-w-3xl px-4 pt-6 pb-16 lg:px-8 lg:pt-8">
      <h1 className="page-title">{r.title}</h1>
      <p className="mt-2 max-w-prose text-pretty text-muted-foreground">{r.lead}</p>
      <PillTabs className="mt-6" label={r.title} value={tab} onChange={setTab} items={TABS.map((k) => ({ value: k, label: r.tabs[k] }))} />
      <div className="mt-6">
        {!rows.data ? (
          <Skeleton className="h-56 w-full" />
        ) : rows.data.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-6 text-muted-foreground">{r.empty}</p>
        ) : (
          <ul className="space-y-4">
            {rows.data.map((row) => (
              <RequestCard key={row.workspace_id} row={row} onDone={() => void rows.mutate()} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
