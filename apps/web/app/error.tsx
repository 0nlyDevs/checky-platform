"use client";

import { StatusPage } from "@/components/status/status-page";

/** A page of this part of Checky that failed to render: its frame stays, the page offers Réessayer. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <StatusPage kind="error" reset={reset} digest={error.digest} />;
}
