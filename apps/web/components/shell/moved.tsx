"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

/** An old section address: replaced by where the section lives now (`to` is under /w/[ws]/). */
export function Moved({ to }: { to: string }) {
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/w/${ws}/${to}` as never);
  }, [router, ws, to]);
  return null;
}
