"use client";

import { ROLES, type Role } from "@fanilo/shared";
import useSWR from "swr";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconCheck, IconMinus } from "@/lib/icons";
import { cn } from "@/lib/utils";

const m = t.team.matrix;

type Permissions = {
  roles: string[];
  capabilities: { key: string; roles: Record<string, boolean>; scope: "own" | null; route: string }[];
};

const isRole = (r: string): r is Role => (ROLES as readonly string[]).includes(r);

/**
 * « Qui peut faire quoi »: every capability against the five roles, as the API reports it from the
 * membership rules its routes really use (`GET /workspaces/{ws}/permissions`). A tick is never
 * colour alone: a check or a dash, and the words for screen readers.
 */
export function PermissionsMatrix({ ws }: { ws: string }) {
  const { data, error } = useSWR<Permissions>(`/workspaces/${ws}/permissions`, fetcher);
  const roles = (data?.roles ?? []).filter(isRole);

  return (
    <section aria-labelledby="matrix-title" className="rounded-lg border border-border bg-card p-5">
      <h2 id="matrix-title" className="font-semibold">
        {m.title}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">{m.lead}</p>
      {error ? (
        <p className="mt-4 text-sm" role="alert">
          {m.failed}
        </p>
      ) : !data ? (
        <Skeleton className="mt-4 h-72 w-full" />
      ) : (
        <>
          {/* Phones scroll the grid sideways; the action column stays put. */}
          <div className="relative mt-4 overflow-x-auto rounded-md border border-border">
            <table className="w-full min-w-[38rem] border-collapse text-sm">
              <caption className="sr-only">{m.title}</caption>
              <thead>
                <tr className="border-b border-foreground">
                  <th scope="col" className="sticky left-0 bg-card px-3 py-2.5 text-left font-medium">
                    {m.capability}
                  </th>
                  {roles.map((r) => (
                    <th key={r} scope="col" className="px-2 py-2.5 text-center font-medium">
                      {t.members.roles[r]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.capabilities.map((c) => (
                  <tr key={c.key}>
                    <th scope="row" className="sticky left-0 bg-card px-3 py-2 text-left font-normal">
                      {m.capabilities[c.key] ?? c.key}
                    </th>
                    {roles.map((r) => {
                      const yes = c.roles[r];
                      const own = yes && c.scope === "own" && r === "journalist";
                      return (
                        <td key={r} className="px-2 py-2 text-center">
                          <span className={cn("inline-flex items-center gap-1", !yes && "text-muted-foreground")}>
                            {yes ? <IconCheck className="size-4" aria-hidden /> : <IconMinus className="size-4" aria-hidden />}
                            <span className={own ? "text-xs" : "sr-only"}>{own ? m.own : yes ? m.yes : m.no}</span>
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">{m.ownNote}</p>
        </>
      )}
    </section>
  );
}

/** The five roles in plain words; `value`/`onChange` turn the list into the invitation's picker. */
export function RolesGuide({ value, onChange, name = "role" }: { value?: Role; onChange?: (r: Role) => void; name?: string }) {
  const r = t.team.roles;
  const pick = !!onChange;
  return (
    <fieldset className="mt-1">
      <legend className={pick ? "text-sm font-medium" : "font-semibold"}>{pick ? t.members.inviteRole : r.title}</legend>
      <p className="mt-0.5 text-sm text-muted-foreground">{r.lead}</p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {ROLES.map((role) => {
          const body = (
            <>
              <span className="block font-medium">{t.members.roles[role]}</span>
              <span className="mt-0.5 block text-sm text-pretty text-muted-foreground">{r.explain[role]}</span>
            </>
          );
          return (
            <li key={role}>
              {pick ? (
                <label
                  className={cn(
                    "block h-full cursor-pointer rounded-md border p-3 has-focus-visible:ring-2 has-focus-visible:ring-ring",
                    value === role ? "border-foreground bg-background ring-1 ring-foreground" : "border-border hover:bg-accent",
                  )}
                >
                  <input type="radio" name={name} value={role} checked={value === role} onChange={() => onChange(role)} className="sr-only" />
                  {body}
                </label>
              ) : (
                <div className="h-full rounded-md border border-border p-3">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
