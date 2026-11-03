"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconArrowLeft } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { EvidenceLine, FlagLabel, flagOf, type Evidence } from "./flag";
import type { Presenter } from "./types";

const s = t.studio;

/** Opened on the studio's tablet: the last three flags the producer sent, in large type, nothing else. */
export function PresenterView() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const { data } = useSWR<Presenter>(`/workspaces/${ws}/studio/${id}/presenter`, fetcher, {
    refreshInterval: 4000,
  });

  return (
    <div className="mx-auto max-w-[70rem] px-6 pt-6 pb-16">
      <nav className="flex items-center justify-between">
        <Link href={`/w/${ws}/studio/${id}` as never} className="inline-flex items-center gap-1.5 text-sm font-bold hover:underline">
          <IconArrowLeft className="size-4" aria-hidden /> {s.presenter.back}
        </Link>
        <span className="text-sm font-bold tracking-wide uppercase">{s.presenter.live}</span>
      </nav>
      <h1 className="mt-4 page-title">{data?.show.title ?? s.presenter.title}</h1>
      {data?.show.status === "ended" && <p className="mt-2 text-lg text-muted-foreground">{s.presenter.ended}</p>}

      {!data?.flags.length ? (
        <p className="mt-10 text-2xl text-pretty text-muted-foreground">{s.presenter.waiting}</p>
      ) : (
        <ul className="mt-8 grid gap-6">
          {data.flags.map((c, i) => {
            const { kind, evidence } = flagOf(c as never);
            return (
              <li
                key={c.id}
                className={cn(
                  "rounded-lg border-2 p-6",
                  i === 0 ? "border-foreground" : "border-border",
                )}
              >
                <p className="text-base font-bold tracking-wide uppercase">{s.presenter.ask}</p>
                <p className={cn("mt-2 text-pretty font-display font-extrabold", i === 0 ? "text-4xl" : "text-2xl")}>
                  {c.question || c.text}
                </p>
                <div className="mt-3">
                  <FlagLabel kind={kind} large={i === 0} />
                </div>
                {i === 0 && (
                  <ul className="mt-4 grid gap-2">
                    {(evidence as Evidence[]).slice(0, 2).map((e, j) => (
                      <li key={j}>
                        <EvidenceLine e={e} large />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
