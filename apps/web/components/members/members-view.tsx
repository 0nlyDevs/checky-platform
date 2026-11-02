"use client";

import type { components, Role } from "@fanilo/shared";
import { ROLES } from "@fanilo/shared";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { IconCheck, IconCircleNotch, IconCopy, IconLink } from "@/lib/icons";
import { toast } from "sonner";
import { Avatar } from "@/components/claims/verdict";
import { PermissionsMatrix, RolesGuide } from "@/components/members/permissions-matrix";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";

type Member = components["schemas"]["MemberOut"];
type Invitation = components["schemas"]["InvitationOut"];

const dateFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

function errorText(e: unknown) {
  return e instanceof ApiError && e.code === "last_admin" ? t.members.lastAdmin : t.detail.saveFailed;
}

function RoleSelect({ value, onChange, id, disabled }: { value: Role; onChange: (r: Role) => void; id?: string; disabled?: boolean }) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Role)} disabled={disabled}>
      <SelectTrigger id={id} className="h-9 w-44 bg-card">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((r) => (
          <SelectItem key={r} value={r}>
            {t.members.roles[r]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Invite({ ws }: { ws: string }) {
  const [role, setRole] = useState<Role>("journalist");
  const [pending, setPending] = useState(false);
  const [invite, setInvite] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const link = invite ? `${window.location.origin}/invitation/${invite.token}` : "";

  async function create() {
    setPending(true);
    try {
      setInvite(await api<Invitation>(`/workspaces/${ws}/invitations`, { method: "POST", body: JSON.stringify({ role }) }));
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
      <div className="mt-4">
        <RolesGuide value={role} onChange={setRole} name="invite-role" />
      </div>
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

export function MembersView() {
  const { ws } = useParams<{ ws: string }>();
  const key = `/workspaces/${ws}/members`;
  const { data: members, error, mutate } = useSWR<Member[]>(key, fetcher);
  const { me, role } = useWorkspace(ws);
  const [confirming, setConfirming] = useState<string | null>(null);
  const isAdmin = role === "admin";
  const label = (m: Member) => m.name ?? m.email ?? m.user_id;

  async function changeRole(m: Member, next: Role) {
    const previous = members;
    mutate(members?.map((x) => (x.user_id === m.user_id ? { ...x, role: next } : x)), { revalidate: false });
    try {
      await api(`${key}/${encodeURIComponent(m.user_id)}`, { method: "PATCH", body: JSON.stringify({ role: next }) });
      toast.success(t.members.roleChanged(label(m)));
      mutate();
    } catch (e) {
      mutate(previous, { revalidate: false });
      toast.error(errorText(e));
    }
  }

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
    <div className="mx-auto max-w-4xl px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <header className="pb-6">
        <h1 className="page-title">{t.members.title}</h1>
        <p className="mt-1 text-muted-foreground">
          {t.members.lead}
          {members && <span className="tabular"> · {t.members.count(members.length)}</span>}
        </p>
      </header>

      {isAdmin ? <Invite ws={ws} /> : role && <p className="text-sm text-muted-foreground">{t.members.adminOnly}</p>}

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
                {isAdmin ? (
                  <div className="flex items-center gap-2">
                    <Label htmlFor={`role-${m.user_id}`} className="sr-only">
                      {t.members.role} — {label(m)}
                    </Label>
                    <RoleSelect id={`role-${m.user_id}`} value={m.role} onChange={(r) => changeRole(m, r)} />
                    {confirming === m.user_id ? (
                      <Button variant="destructive" size="sm" className="h-9" onClick={() => remove(m)} onBlur={() => setConfirming(null)} autoFocus>
                        {t.members.removeConfirm(self ? t.members.you : label(m))}
                      </Button>
                    ) : (
                      <Button variant="ghost" size="sm" className="h-9 text-muted-foreground" onClick={() => setConfirming(m.user_id)}>
                        {t.members.remove}
                      </Button>
                    )}
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">{t.members.roles[m.role]}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* Who may do what, read from the API's own rules; non-admins also get the roles in words. */}
      <div className="mt-8 space-y-8">
        {role && !isAdmin && (
          <section className="rounded-lg border border-border bg-card p-5">
            <RolesGuide />
          </section>
        )}
        {role && <PermissionsMatrix ws={ws} />}
      </div>
    </div>
  );
}
