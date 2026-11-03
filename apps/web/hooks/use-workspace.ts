"use client";

import type { Me } from "@checky/shared";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { components } from "@checky/shared";

type Member = components["schemas"]["MemberOut"];

/** Whether I belong to the workspace (every member is one of its journalists) and a user id →
 * display name lookup. */
export function useWorkspace(ws: string) {
  const { data: me } = useSWR<Me>("/me", fetcher);
  const { data: members } = useSWR<Member[]>(`/workspaces/${ws}/members`, fetcher);
  const joined = Boolean(me?.memberships.some((m) => m.workspace_id === ws));
  const names = new Map((members ?? []).map((m) => [m.user_id, m.name ?? m.email ?? m.user_id]));
  return { me, joined, names, members };
}
