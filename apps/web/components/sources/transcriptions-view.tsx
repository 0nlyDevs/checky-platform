"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

/** Old address: recordings are now a tab of Sources. */
export function TranscriptionsView() {
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/w/${ws}/sources?vue=enregistrements`);
  }, [router, ws]);
  return null;
}
