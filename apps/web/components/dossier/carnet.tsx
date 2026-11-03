"use client";

import type { Item } from "@checky/shared";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { VerdictChip } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, downloadFile, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconCircleNotch, IconCopy, IconDownloadSimple, IconFileText, IconPrinter, IconSealCheck, IconX } from "@/lib/icons";
import { type Attestation, type Carnet, fmtDay, fmtWhen } from "./types";

const c = t.dossier.carnet;

// While a sheet is open, printing prints the sheet alone, in ink on white.
const PRINT_CSS = `
@media print {
  @page { size: A4; margin: 16mm; }
  body * { visibility: hidden !important; }
  .print-sheet, .print-sheet * { visibility: visible !important; }
  .print-sheet { position: absolute !important; inset: 0 auto auto 0 !important; width: 100% !important; overflow: visible !important; background: #fff !important; color: #0a0a0b !important; }
  .no-print { display: none !important; }
}`;

/** « Enregistrer en PDF »: the server draws the A4 (`carnet-FAN-0142.pdf`), the same on every device. */
function PdfButton({ path, name, disabled }: { path: string; name: string; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      disabled={busy || disabled}
      onClick={async () => {
        setBusy(true);
        try {
          await downloadFile(path, name);
        } catch {
          toast.error(c.pdfFailed);
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconDownloadSimple aria-hidden />}
      {busy ? c.pdfBusy : c.pdf}
    </Button>
  );
}

/** A full-page sheet over the dossier, made to be read on screen, saved as a PDF or printed. */
function Sheet({ title, onClose, pdf, children }: { title: string; onClose: () => void; pdf: React.ReactNode; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal aria-label={title} className="print-sheet fixed inset-0 z-50 overflow-y-auto bg-background">
      <style>{PRINT_CSS}</style>
      <div className="no-print sticky top-0 z-10 flex justify-end gap-2 border-b border-border bg-background px-4 py-3 lg:px-8">
        {pdf}
        <Button variant="outline" onClick={() => window.print()}>
          <IconPrinter aria-hidden />
          {c.print}
        </Button>
        <Button variant="ghost" onClick={onClose} autoFocus>
          <IconX aria-hidden />
          {c.close}
        </Button>
      </div>
      <article className="mx-auto max-w-3xl px-4 py-8 lg:px-8">{children}</article>
    </div>
  );
}

function CarnetSheet({ ws, item, onClose }: { ws: string; item: Item; onClose: () => void }) {
  const { data, error } = useSWR<Carnet>(`/workspaces/${ws}/items/${item.id}/carnet`, fetcher);
  const ref = (item.data as { ref?: string }).ref ?? "dossier";
  return (
    <Sheet title={c.title} onClose={onClose} pdf={<PdfButton path={`/workspaces/${ws}/items/${item.id}/carnet.pdf`} name={`carnet-${ref}.pdf`} />}>
      {error && <p>{c.failed}</p>}
      {!data && !error && <Skeleton className="h-64 w-full" />}
      {data && (
        <div className="space-y-8">
          <header className="border-b-2 border-foreground pb-4">
            <p className="flex justify-between gap-4 text-sm text-muted-foreground">
              <span>{data.newsroom}</span>
              <span className="font-display font-bold text-foreground tabular">{data.ref}</span>
            </p>
            <h1 className="mt-2 font-display text-2xl font-extrabold text-pretty">{c.title}</h1>
            <p className="mt-1 text-lg text-pretty">{t.common.quote(data.title)}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              {c.generated(fmtWhen(data.generated_at) ?? "")} · {c.summary(data.entries.length, data.sources.length, data.questions.length)}
            </p>
            {data.verdict && (
              <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                <VerdictChip verdict={data.verdict} />
                {data.byline?.journalist && <span>{t.dossier.sign.signedBy(data.byline.journalist, data.byline.newsroom ?? data.newsroom, fmtWhen(data.byline.signed_at) ?? "")}</span>}
              </p>
            )}
            {data.reason && <p className="mt-2 text-pretty">{data.reason}</p>}
          </header>

          <section>
            <h2 className="font-display text-lg font-bold">{c.entries}</h2>
            <ol className="mt-3 divide-y divide-border border-y border-border">
              {data.entries.map((e, i) => (
                <li key={i} className="grid gap-x-4 py-2 text-sm sm:grid-cols-[9.5rem_minmax(0,1fr)]">
                  <time dateTime={e.at} className="text-muted-foreground tabular">
                    {fmtWhen(e.at)}
                  </time>
                  <p className="text-pretty">
                    <span className="font-medium">{e.actor}</span> · {e.text}
                  </p>
                </li>
              ))}
            </ol>
          </section>

          <section>
            <h2 className="font-display text-lg font-bold">{c.sources}</h2>
            {data.sources.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">{c.noSources}</p>
            ) : (
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">
                {data.sources.map((s) => (
                  <li key={s.id} className="text-pretty">
                    <span className="font-medium">{s.title}</span>
                    {s.url && <span className="block break-all text-muted-foreground">{s.url}</span>}
                    <span className="block text-muted-foreground">
                      {s.published_at ? c.published(fmtDay(s.published_at) ?? s.published_at) : t.dossier.carnet.added(fmtWhen(s.added_at) ?? "")} · {s.added_by}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section>
            <h2 className="font-display text-lg font-bold">{c.questions}</h2>
            {data.questions.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">{c.noQuestions}</p>
            ) : (
              <ul className="mt-3 space-y-1.5 text-sm">
                {data.questions.map((q, i) => (
                  <li key={i}>
                    <span className="font-medium">{[q.contact, q.institution].filter(Boolean).join(", ") || "—"}</span> · {t.dossier.who.channels[q.channel] ?? q.channel} ·{" "}
                    {q.answered_at ? c.answered(fmtWhen(q.answered_at) ?? "", t.dossier.who.stances[q.stance ?? ""] ?? q.stance ?? "") : c.notAnswered}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </Sheet>
  );
}

function AttestationSheet({ ws, item, onClose }: { ws: string; item: Item; onClose: () => void }) {
  const { data, error } = useSWR<Attestation>(`/workspaces/${ws}/items/${item.id}/attestation`, fetcher, { revalidateOnFocus: false });
  const code = error instanceof ApiError ? error.code : null;
  const ref = (item.data as { ref?: string }).ref ?? "dossier";
  return (
    <Sheet
      title={c.attestation}
      onClose={onClose}
      pdf={<PdfButton path={`/workspaces/${ws}/items/${item.id}/attestation.pdf`} name={`attestation-${ref}.pdf`} disabled={!data} />}
    >
      {error && <p>{code === "not_signed" ? c.notSigned : code === "attestation_unavailable" ? c.unavailable : c.failed}</p>}
      {!data && !error && <Skeleton className="h-64 w-full" />}
      {data && (
        <div className="space-y-6">
          <header className="border-b-2 border-foreground pb-4">
            <h1 className="flex items-center gap-2 font-display text-2xl font-extrabold">
              <IconSealCheck className="size-6" aria-hidden />
              {c.attestation}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{c.attIssued(fmtWhen(data.issued_at) ?? data.issued_at)}</p>
          </header>
          <p className="text-lg text-pretty">{data.summary}</p>
          <p className="text-sm text-muted-foreground">{c.attLead}</p>
          <dl className="space-y-3 text-sm">
            {[
              [c.attSha, data.sha256],
              [c.attKey, `${data.key_id} · ${data.public_key}`],
              [c.attSignature, data.signature],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="font-bold">{k}</dt>
                <dd className="font-mono text-xs break-all">{v}</dd>
              </div>
            ))}
          </dl>
          <pre className="overflow-x-auto rounded-md border border-border bg-card p-3 text-xs whitespace-pre-wrap">{JSON.stringify(data.payload, null, 2)}</pre>
          <p className="text-sm text-muted-foreground">{c.attVerify}</p>
          <Button
            variant="outline"
            className="no-print"
            onClick={async () => {
              await navigator.clipboard.writeText(JSON.stringify({ payload: data.payload, signature: data.signature }, null, 2)).catch(() => null);
              toast.success(c.attCopied);
            }}
          >
            <IconCopy aria-hidden />
            {c.attCopy}
          </Button>
        </div>
      )}
    </Sheet>
  );
}

/** « Carnet de diligence » and « Attestation »: what was done on the dossier, to print or hand over. */
export function CarnetPanel({ ws, item }: { ws: string; item: Item }) {
  const [open, setOpen] = useState<"carnet" | "attestation" | null>(null);
  const signed = Boolean(item.data.signed_by);
  return (
    <section aria-labelledby="carnet" className="space-y-3">
      <h2 id="carnet" className="font-display text-xl font-bold">
        {c.title}
      </h2>
      <p className="max-w-[70ch] text-sm text-muted-foreground">{c.lead}</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setOpen("carnet")}>
          <IconFileText aria-hidden />
          {c.export}
        </Button>
        <Button variant="outline" onClick={() => setOpen("attestation")} disabled={!signed} title={signed ? undefined : c.notSigned}>
          <IconSealCheck aria-hidden />
          {c.attestation}
        </Button>
      </div>
      {!signed && <p className="text-sm text-muted-foreground">{c.notSigned}</p>}
      {open === "carnet" && <CarnetSheet ws={ws} item={item} onClose={() => setOpen(null)} />}
      {open === "attestation" && <AttestationSheet ws={ws} item={item} onClose={() => setOpen(null)} />}
    </section>
  );
}
