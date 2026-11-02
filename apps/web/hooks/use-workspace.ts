"use client";

import type { Me, Role } from "@fanilo/shared";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { components } from "@fanilo/shared";

type Member = components["schemas"]["MemberOut"];

/** My role in the workspace and a user id → display name lookup. */
export function useWorkspace(ws: string) {
  const { data: me } = useSWR<Me>("/me", fetcher);
  const { data: members } = useSWR<Member[]>(`/workspaces/${ws}/members`, fetcher);
  const role = me?.memberships.find((m) => m.workspace_id === ws)?.role as Role | undefined;
  const names = new Map((members ?? []).map((m) => [m.user_id, m.name ?? m.email ?? m.user_id]));
  return { me, role, names, members };
}
