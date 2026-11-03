"use client";

import type { Me } from "@checky/shared";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

/** Me and whether I belong here, without the member list. */
export function useMe(ws: string) {
  const { data: me } = useSWR<Me>("/me", fetcher);
  const joined = Boolean(me?.memberships.some((m) => m.workspace_id === ws));
  return { me, joined };
}
