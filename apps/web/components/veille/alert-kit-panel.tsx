"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { IconCircleNotch, IconPhone, IconRadio, IconShieldCheck } from "@/lib/icons";
import { API_URL, api, fetcher } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Call = { contact_id: string; name: string; institution: string; office: string; region: string | null; phone: string | null; whatsapp: string | null; why: string; is_demo: boolean };
type Kit = {
  status: "draft" | "approved"; written_by: string; known: string[]; unknown: string[];
  script: { fr: string; mg: string }; call: Call[]; dont_say: string[];
  guards: { names?: number; numbers?: number; alarm?: number }; stale: boolean;
  approved_name?: string | null; mg_hash: string | null;
  relu_mg: { name: string; current: boolean } | null;
};
type Radio = { id: string; station: string; region: string | null; in_region: boolean; sent: boolean; has_contact: boolean; is_demo: boolean };
type State = { kit: Kit | null; radios: Radio[]; trajet: { id: string; place: string; status: string }[] };
type SendResult = { state: State; links: { radio_id: string; station: string; whatsapp: string | null; sms_queued: boolean; sms_simulated: boolean }[]; mg: boolean };
type Edits = { known: string; unknown: string; script_fr: string; script_mg: string; dont_say: string; call_ids: string[] };

const lines = (value: string) => value.split("\n").map((line) => line.trim()).filter(Boolean);
const field = "min-h-24 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function AlertKitPanel({ ws, alertId, onChanged }: { ws: string; alertId: string; onChanged: () => void }) {
  const t = useT().alertKit;
  const base = `/workspaces/${ws}/alerts/${alertId}`;
  const { data, error, isLoading, mutate } = useSWR<State>(`${base}/kit`, fetcher);
  const [busy, setBusy] = useState("");
  const [withoutAi, setWithoutAi] = useState(false);
  const [edits, setEdits] = useState<Edits | null>(null);
  const [desk, setDesk] = useState(true);
  const [selected, setSelected] = useState<string[] | null>(null);
  const [sent, setSent] = useState<SendResult["links"]>([]);
  const [reason, setReason] = useState("");
  const kit = data?.kit;
  const chosen = selected ?? data?.radios.filter((radio) => radio.in_region).map((radio) => radio.id) ?? [];

  async function act(name: string, path: string, method: "POST" | "PUT", body: object) {
    setBusy(name);
    try {
      const state = await api<State>(`${base}${path}`, { method, body: JSON.stringify(body) });
      await mutate(state, { revalidate: false });
      onChanged();
      return state;
    } catch {
      toast.error(t.failed);
      return null;
    } finally {
      setBusy("");
    }
  }

  function beginEdit() {
    if (!kit) return;
    setEdits({ known: kit.known.join("\n"), unknown: kit.unknown.join("\n"), script_fr: kit.script.fr,
      script_mg: kit.script.mg, dont_say: kit.dont_say.join("\n"), call_ids: kit.call.map((c) => c.contact_id) });
  }

  async function approve() {
    const body = edits ? { known: lines(edits.known), unknown: lines(edits.unknown), script_fr: edits.script_fr,
      script_mg: edits.script_mg, dont_say: lines(edits.dont_say), call_ids: edits.call_ids } : {};
    if (await act("approve", "/kit", "PUT", body)) {
      setEdits(null);
      toast.success(t.saved);
    }
  }

  async function send() {
    setBusy("send");
    try {
      const result = await api<SendResult>(`${base}/kit/send`, { method: "POST", body: JSON.stringify({ radio_ids: chosen, desks: desk }) });
      await mutate(result.state, { revalidate: false });
      setSent(result.links);
      onChanged();
      toast.success(t.sent(desk, result.links.length));
    } catch {
      toast.error(t.failed);
    } finally {
      setBusy("");
    }
  }

  async function close() {
    if (reason.trim().length < 3) return;
    setBusy("close");
    try {
      await api(`${base}/close`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) });
      toast.success(t.closed);
      onChanged();
    } catch {
      toast.error(t.failed);
    } finally {
      setBusy("");
    }
  }

  if (isLoading) return <p className="mt-4 text-sm text-muted-foreground" role="status">{t.preparing}</p>;
  if (error || !data) return <p className="mt-4 text-sm text-muted-foreground" role="alert">{t.loadFailed}</p>;

  return (
    <section className="mt-5 space-y-5 border-t border-border pt-5" aria-label={t.title}>
      <div>
        <h3 className="font-display text-lg font-bold">{t.title}</h3>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t.lead}</p>
      </div>
      {!kit && (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void act("draft", "/kit", "POST", { ai: !withoutAi })} disabled={Boolean(busy)}>
            {busy === "draft" && <IconCircleNotch className="animate-spin" aria-hidden />}
            {busy === "draft" ? t.preparing : t.prepare}
          </Button>
          <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={withoutAi} onChange={(e) => setWithoutAi(e.target.checked)} />{t.withoutAi}</label>
        </div>
      )}
      {kit && (
        <>
          <div className={`space-y-4 rounded-xl border p-4 ${kit.status === "draft" ? "border-dashed" : "border-solid"}`}>
            <div className="flex flex-wrap items-center gap-2 text-sm font-bold">
              <IconShieldCheck className="size-5" aria-hidden />
              <span>{kit.status === "draft" ? t.draft : t.approved(kit.approved_name ?? "")}</span>
            </div>
            <p className="text-sm text-muted-foreground">{t.writtenBy[kit.written_by] ?? kit.written_by}</p>
            {kit.stale && <p className="text-sm font-bold" role="alert">{t.stale}</p>}
            {Boolean(kit.guards.names || kit.guards.numbers || kit.guards.alarm) && (
              <p className="text-sm text-muted-foreground">{t.guards(kit.guards.names ?? 0, kit.guards.numbers ?? 0, kit.guards.alarm ?? 0)}</p>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <TextList title={t.known} value={kit.known} edited={edits?.known} onChange={(v) => setEdits((e) => e && { ...e, known: v })} />
              <TextList title={t.unknown} value={kit.unknown} edited={edits?.unknown} onChange={(v) => setEdits((e) => e && { ...e, unknown: v })} />
            </div>
            <div className="space-y-3">
              <h4 className="font-bold">{t.script}</h4>
              <TextList title={t.scriptFr} value={[kit.script.fr]} edited={edits?.script_fr} onChange={(v) => setEdits((e) => e && { ...e, script_fr: v })} />
              <TextList title={t.scriptMg} value={[kit.script.mg]} edited={edits?.script_mg} onChange={(v) => setEdits((e) => e && { ...e, script_mg: v })} />
            </div>
            <div>
              <h4 className="font-bold">{t.call}</h4>
              {kit.call.length ? <ul className="mt-2 space-y-2">{kit.call.map((c) => (
                <li key={c.contact_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  {edits && <input type="checkbox" aria-label={c.name} checked={edits.call_ids.includes(c.contact_id)} onChange={(e) => setEdits((old) => old && ({ ...old, call_ids: e.target.checked ? [...old.call_ids, c.contact_id] : old.call_ids.filter((id) => id !== c.contact_id) }))} />}
                  <strong>{c.name}</strong><span className="text-muted-foreground">{c.why}</span>
                  {c.is_demo && <span className="text-muted-foreground">{t.callDemo}</span>}
                  {c.phone && <a className="inline-flex items-center gap-1 underline" href={`tel:${c.phone}`}><IconPhone className="size-4" aria-hidden />{c.phone}</a>}
                </li>
              ))}</ul> : <p className="mt-1 text-sm text-muted-foreground">{t.noCall}</p>}
            </div>
            <TextList title={t.dontSay} value={kit.dont_say} edited={edits?.dont_say} onChange={(v) => setEdits((e) => e && { ...e, dont_say: v })} />
            {edits && <p className="text-sm text-muted-foreground">{t.editing}</p>}
            <div className="flex flex-wrap gap-2">
              {edits ? <><Button onClick={() => void approve()} disabled={Boolean(busy)}>{busy === "approve" ? t.saving : t.save}</Button><Button variant="outline" onClick={() => setEdits(null)}>{t.cancel}</Button></> :
                <><Button variant={kit.status === "draft" ? "default" : "outline"} onClick={() => kit.status === "draft" ? void approve() : beginEdit()} disabled={Boolean(busy)}>{kit.status === "draft" ? t.save : t.edit}</Button>
                  {kit.status === "draft" && <Button variant="outline" onClick={beginEdit}>{t.edit}</Button>}</>}
              <Button variant="outline" onClick={() => void act("draft", "/kit", "POST", { ai: !withoutAi })} disabled={Boolean(busy)}>{t.prepare}</Button>
            </div>
          </div>
          {kit.status === "approved" && (
            <div className="space-y-4">
              <div>
                <label className="inline-flex items-center gap-2 text-sm font-bold"><input type="checkbox" checked={Boolean(kit.relu_mg?.current)} onChange={() => void act("relu", kit.relu_mg?.current ? "/kit/relu-mg" : "/kit/relu-mg", "POST", { mg_hash: kit.mg_hash })} disabled={!kit.mg_hash || Boolean(busy) || Boolean(kit.relu_mg?.current)} />{t.mgReviewed}</label>
                <p className="mt-1 text-sm text-muted-foreground">{kit.relu_mg?.current ? t.mgReviewedBy(kit.relu_mg.name) : kit.relu_mg ? t.mgStale : t.mgLead}</p>
              </div>
              <div>
                <h4 className="font-bold">{t.sendTitle}</h4>
                <p className="mt-1 text-sm text-muted-foreground">{t.sendLead}</p>
                <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={desk} onChange={(e) => setDesk(e.target.checked)} />{t.desks}</label>
                {data.radios.length ? <ul className="mt-2 grid gap-2 sm:grid-cols-2">{data.radios.map((r) => (
                  <li key={r.id}><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={chosen.includes(r.id)} onChange={(e) => setSelected(e.target.checked ? [...chosen, r.id] : chosen.filter((id) => id !== r.id))} />
                    <IconRadio className="size-4" aria-hidden />{r.station}{r.in_region && <span className="text-muted-foreground">· {t.inRegion}</span>}{r.is_demo && <span className="text-muted-foreground">· {t.callDemo}</span>}</label></li>
                ))}</ul> : <p className="mt-2 text-sm text-muted-foreground">{t.noRadios}</p>}
                <Button className="mt-3" onClick={() => void send()} disabled={Boolean(busy) || (!desk && chosen.length === 0)}>{busy === "send" ? t.sending : t.send}</Button>
                {sent.length > 0 && <ul className="mt-3 space-y-1 text-sm">{sent.map((r) => <li key={r.radio_id} className="flex flex-wrap items-center gap-2"><strong>{r.station}</strong>{r.whatsapp && <a href={`${API_URL}/api/v1${r.whatsapp}`} target="_blank" rel="noreferrer" className="underline">{t.openWhatsapp}</a>}{r.sms_queued && <span>{r.sms_simulated ? t.smsSimulated : t.smsQueued}</span>}{!r.whatsapp && !r.sms_queued && <span>{t.noNumber}</span>}</li>)}</ul>}
                {data.trajet.length > 0 && <p className="mt-3 text-sm text-muted-foreground">{t.sentLine(data.trajet.length)}</p>}
              </div>
            </div>
          )}
        </>
      )}
      <div className="border-t border-border pt-4">
        <h4 className="font-bold">{t.close}</h4>
        <p className="mt-1 text-sm text-muted-foreground">{t.closeLead}</p>
        <label className="mt-3 block text-sm font-medium" htmlFor={`close-${alertId}`}>{t.closeReason}</label>
        <textarea id={`close-${alertId}`} className={`${field} mt-1 min-h-16`} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
        <Button variant="outline" className="mt-2" onClick={() => void close()} disabled={reason.trim().length < 3 || Boolean(busy)}>{busy === "close" ? t.saving : t.closeConfirm}</Button>
      </div>
    </section>
  );
}

function TextList({ title, value, edited, onChange }: { title: string; value: string[]; edited?: string; onChange: (value: string) => void }) {
  return <div><h4 className="text-sm font-bold">{title}</h4>{edited === undefined ? <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">{value.map((line, i) => <li key={`${i}-${line}`}>{line}</li>)}</ul> :
    <textarea aria-label={title} className={`${field} mt-1`} value={edited} onChange={(e) => onChange(e.target.value)} />}</div>;
}
