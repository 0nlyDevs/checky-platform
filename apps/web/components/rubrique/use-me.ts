"use client";

import type { Me, Role } from "@fanilo/shared";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

/** Me and my role here, without the member list (a veilleur may not read it). */
export function useMe(ws: string) {
  const { data: me } = useSWR<Me>("/me", fetcher);
  const role = me?.memberships.find((m) => m.workspace_id === ws)?.role as Role | undefined;
  return { me, role };
}
