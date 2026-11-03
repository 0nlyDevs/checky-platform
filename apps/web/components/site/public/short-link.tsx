"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { IconArrowRight, IconCircleNotch } from "@/lib/icons";
import { publicApi } from "@/lib/public-api";

/** `/v/145`, the short link an SMS or a flash carries: finds the newest public verdict with that
 *  number and opens its page. */
export function ShortLink() {
  const { ref } = useParams<{ ref: string }>();
  const router = useRouter();
  const s = useT().publicLayer.short;
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let live = true;
    publicApi<{ id: string }>(`/v/${encodeURIComponent(ref)}`)
      .then((v) => live && router.replace(`/verdicts/${v.id}`))
      .catch(() => live && setMissing(true));
    return () => {
      live = false;
    };
  }, [ref, router]);

  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-10 pb-20 lg:px-10 lg:pt-14" aria-live="polite">
      {missing ? (
        <>
          <p className="text-xl">{s.notFound}</p>
          <Link href="/verdicts" className="mt-4 inline-flex items-center gap-1.5 font-bold underline underline-offset-4">
            {s.all} <IconArrowRight className="size-4" aria-hidden />
          </Link>
        </>
      ) : (
        <p className="flex items-center gap-2 text-lg">
          <IconCircleNotch className="size-5 animate-spin" aria-hidden />
          {s.finding}
        </p>
      )}
    </div>
  );
}
