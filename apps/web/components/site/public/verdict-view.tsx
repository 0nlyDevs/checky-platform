"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { VerdictFile } from "@/components/site/public/verdict-file";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, publicApi } from "@/lib/public-api";

const p = t.site.pub.file;

/** One published verdict, its sources and the text the newsroom published, with a shareable link. */
export function VerdictView() {
  const { id } = useParams<{ id: string }>();
  const [v, setV] = useState<PublicVerdict | null | "missing">(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    publicApi<PublicVerdict>(`/verdicts/${id}`).then(setV).catch(() => setV("missing"));
  }, [id]);

  return (
    <section className="frame-x pt-[clamp(32px,6vw,72px)] pb-[clamp(72px,9vw,130px)]" aria-labelledby="verdict-title">
      <Link href="/verifies" className="ulink typed text-[15px]">
        ← {p.back}
      </Link>
      <h1 id="verdict-title" className="sr-only">
        {v && v !== "missing" ? v.title : p.open}
      </h1>
      <div className="mx-auto mt-8 max-w-3xl">
        {v === "missing" && <p className="text-xl">{p.notFound}</p>}
        {v && v !== "missing" && (
          <>
            <VerdictFile v={v} full />
            <button
              type="button"
              className="tab-btn mt-8"
              onClick={() => navigator.clipboard?.writeText(location.href).then(() => setCopied(true))}
            >
              {copied ? p.copied : p.share}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
