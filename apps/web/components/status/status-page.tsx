"use client";

import Link from "next/link";
import { Wordmark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n";

/**
 * What a visitor sees when a page does not exist or failed to render, in the page's language:
 * the wordmark, a plain title, one line, and the way back (Réessayer first after an error).
 * Never a stack trace; the error's digest only, to quote to the team.
 */
export function StatusPage({ kind, reset, digest }: { kind: "notFound" | "error"; reset?: () => void; digest?: string }) {
  const t = useT();
  const p = kind === "notFound" ? t.pages.notFound : t.pages.error;
  return (
    <main className="mx-auto flex min-h-[70vh] max-w-xl flex-col justify-center gap-6 px-6 py-16">
      <Link href="/" aria-label="Checky" className="self-start">
        <Wordmark className="h-7" />
      </Link>
      <div>
        <h1 className="page-title text-balance">{p.title}</h1>
        <p className="mt-3 text-lg text-pretty text-muted-foreground">{p.lead}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {kind === "error" && reset && (
          <Button variant="action" size="lg" onClick={reset}>
            {t.pages.error.retry}
          </Button>
        )}
        <Button asChild variant={kind === "error" && reset ? "outline" : "action"} size="lg">
          <Link href="/">{p.home}</Link>
        </Button>
      </div>
      {kind === "error" && digest && <p className="text-sm text-muted-foreground tabular">{t.pages.error.code(digest)}</p>}
    </main>
  );
}
