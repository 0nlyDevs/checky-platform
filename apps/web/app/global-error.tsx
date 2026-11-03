"use client";

import { StatusPage } from "@/components/status/status-page";
import "./globals.css";

/** Even the root layout failed: this page brings its own <html> and stylesheet. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="fr">
      <body className="bg-background text-foreground">
        <StatusPage kind="error" reset={reset} digest={error.digest} />
      </body>
    </html>
  );
}
