"use client";

import type { components } from "@checky/shared";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { IconCheck, IconCircleNotch, IconCopy, IconLink } from "@/lib/icons";
import { toast } from "sonner";
import { Avatar } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, ApiError, fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";

type Member = components["schemas"]["MemberOut"];
type Invitation = components["schemas"]["InvitationOut"];

const dateFmt = dateFormat({ day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

function errorText(e: unknown) {
  return e instanceof ApiError && e.code === "last_member" ? t.members.lastMember : t.detail.saveFailed;
}

function Invite({ ws }: { ws: string }) {
  const [pending, setPending] = useState(false);
  const [invite, setInvite] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const link = invite ? `${window.location.origin}/invitation/${invite.token}` : "";

  async function create() {
    setPending(true);
    try {
      setInvite(await api<Invitation>(`/workspaces/${ws}/invitations`, { method: "POST" }));
      setCopied(false);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setPending(false);
    }
  }

  async function copy() {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    toast.success(t.members.copied);
  }

  return (
    <section aria-labelledby="invite-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="invite-title" className="font-semibold">
        {t.members.inviteTitle}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t.members.inviteLead}</p>
      <Button onClick={create} disabled={pending} className="mt-4 h-9">
        {pending ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconLink aria-hidden />}
        {t.members.createLink}
      </Button>
      {invite && (
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-md bg-muted p-2 pl-3">
          <code className="min-w-0 flex-1 truncate text-sm" title={link}>
            {link}
          </code>
          <Button variant="outline" size="sm" onClick={copy}>
            {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
            {t.members.copy}
          </Button>
          <p className="w-full text-xs text-muted-foreground">{t.members.expires(dateFmt.format(new Date(invite.expires_at)))}</p>
        </div>
      )}
    </section>
  );
}

/** The team, as a section of Réglages (`embedded`) or on its own. */
export function MembersView({ embedded = false }: { embedded?: boolean }) {
  const { ws } = useParams<{ ws: string }>();
  const key = `/workspaces/${ws}/members`;
  const { data: members, error, mutate } = useSWR<Member[]>(key, fetcher);
  const { me } = useWorkspace(ws);
  const [confirming, setConfirming] = useState<string | null>(null);
  const label = (m: Member) => m.name ?? m.email ?? m.user_id;

  async function remove(m: Member) {
    setConfirming(null);
    try {
      await api(`${key}/${encodeURIComponent(m.user_id)}`, { method: "DELETE" });
      toast.success(t.members.removed(label(m)));
      mutate();
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  return (
    <div id="equipe" className={embedded ? "scroll-mt-24" : "mx-auto max-w-4xl px-4 pt-6 pb-12 lg:px-8 lg:pt-8"}>
      <header className="pb-6">
        {embedded ? <h2 className="font-display text-xl font-bold">{t.members.title}</h2> : <h1 className="page-title">{t.members.title}</h1>}
        <p className="mt-1 text-muted-foreground">
          {t.members.lead}
          {members && <span className="tabular"> · {t.members.count(members.length)}</span>}
        </p>
      </header>

      <Invite ws={ws} />

      {error ? (
        <div className="mt-6">
          <p className="text-muted-foreground">{t.claims.errorTitle}</p>
          <Button variant="outline" className="mt-3" onClick={() => mutate()}>
            {t.claims.retry}
          </Button>
        </div>
      ) : !members ? (
        <Skeleton className="mt-6 h-48 w-full" />
      ) : (
        <ul className="mt-6 divide-y divide-border rounded-lg border border-border bg-card">
          {members.map((m) => {
            const self = m.user_id === me?.id;
            return (
              <li key={m.user_id} className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5">
                <Avatar name={label(m)} className="size-9 text-sm" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {label(m)}
                    {self && <span className="font-normal text-muted-foreground"> ({t.members.you})</span>}
                  </p>
                  {m.email && m.name && <p className="truncate text-sm text-muted-foreground">{m.email}</p>}
                </div>
                {members.length > 1 &&
                  (confirming === m.user_id ? (
                    <Button variant="destructive" size="sm" className="h-9" onClick={() => remove(m)} onBlur={() => setConfirming(null)} autoFocus>
                      {t.members.removeConfirm(self ? t.members.you : label(m))}
                    </Button>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-9 text-muted-foreground" onClick={() => setConfirming(m.user_id)}>
                      {self ? t.members.leave : t.members.remove}
                    </Button>
                  ))}
              </li>
            );
          })}
        </ul>
      )}

    </div>
  );
}
