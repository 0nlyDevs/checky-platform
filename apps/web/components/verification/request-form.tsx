"use client";

import type { components } from "@fanilo/shared";
import { useState } from "react";
import { toast } from "sonner";
import useSWR, { mutate as globalMutate } from "swr";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconCircleNotch, IconLockSimple } from "@/lib/icons";

export type Verification = components["schemas"]["VerificationOut"];
type Country = components["schemas"]["CountryOut"];

const v = t.verification;
const field =
  "mt-1 h-11 w-full rounded-md border border-input bg-card px-3 text-base outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15";
const KINDS = ["radio", "tv", "press", "online"] as const;

export function useVerification(ws: string) {
  return useSWR<Verification>(`/workspaces/${ws}/verification`, fetcher);
}

function Field({ name, label, hint, ...rest }: { name: string; label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="text-sm font-bold">{label}</span>
      <input name={name} className={field} {...rest} />
      {hint && <span className="mt-1 block text-sm text-muted-foreground">{hint}</span>}
    </label>
  );
}

/**
 * The request a newsroom sends to be verified. Prefilled from the last request (to correct it after
 * a refusal) or with the newsroom's name. The personal data only reaches the Checky team.
 */
export function RequestForm({ ws, outlet, onSent, onLater }: { ws: string; outlet?: string; onSent?: () => void; onLater?: () => void }) {
  const { data, mutate } = useVerification(ws);
  const countries = useSWR<Country[]>("/public/countries", fetcher, { revalidateOnFocus: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const r = data?.request;

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const get = (k: string) => String(f.get(k) ?? "").trim();
    setBusy(true);
    setError(null);
    try {
      const out = await api<Verification>(`/workspaces/${ws}/verification`, {
        method: "PUT",
        body: JSON.stringify({
          outlet: get("outlet"),
          kind: get("kind"),
          city: get("city"),
          region: get("region") || null,
          country: get("country"),
          website: get("website"),
          full_name: get("full_name"),
          job_title: get("job_title"),
          phone: get("phone"),
          email: get("email"),
          press_card: get("press_card") || null,
        }),
      });
      await mutate(out, { revalidate: false });
      toast.success(v.form.sent);
      if (onSent) onSent();
      else void globalMutate("/me");
      void globalMutate(`/workspaces/${ws}`);
    } catch (err) {
      setError(v.form.errors[err instanceof ApiError ? err.code : "generic"] ?? v.form.errors.generic);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <Skeleton className="h-[34rem] w-full" />;
  return (
    <form key={data.status} onSubmit={submit} className="space-y-6">
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-3 font-display text-lg font-bold">{v.form.outletBlock}</legend>
        <Field name="outlet" label={v.form.outlet} required minLength={2} maxLength={160} defaultValue={r?.outlet ?? outlet} />
        <label className="block">
          <span className="text-sm font-bold">{v.form.kind}</span>
          <select name="kind" required defaultValue={r?.kind ?? "radio"} className={field}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {v.kinds[k]}
              </option>
            ))}
          </select>
        </label>
        <Field name="city" label={v.form.city} required minLength={2} maxLength={120} defaultValue={r?.city} autoComplete="address-level2" />
        <Field name="region" label={v.form.region} maxLength={120} defaultValue={r?.region ?? ""} autoComplete="address-level1" />
        <label className="block">
          <span className="text-sm font-bold">{v.form.country}</span>
          <select name="country" required defaultValue={r?.country ?? "MG"} className={field}>
            {(countries.data ?? [{ code: "MG", name: "Madagascar" }]).map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <Field
          name="website"
          label={v.form.website}
          hint={v.form.websiteHint}
          required
          maxLength={500}
          inputMode="url"
          placeholder="facebook.com/…"
          defaultValue={r?.website}
        />
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-3 font-display text-lg font-bold">{v.form.personBlock}</legend>
        <Field name="full_name" label={v.form.fullName} required minLength={3} maxLength={160} defaultValue={r?.full_name} autoComplete="name" />
        <Field name="job_title" label={v.form.jobTitle} required minLength={2} maxLength={120} defaultValue={r?.job_title} autoComplete="organization-title" />
        <Field name="phone" label={v.form.phone} required type="tel" maxLength={32} defaultValue={r?.phone} autoComplete="tel" />
        <Field name="email" label={v.form.email} required type="email" maxLength={254} defaultValue={r?.email} autoComplete="email" />
        <Field name="press_card" label={v.form.pressCard} maxLength={120} defaultValue={r?.press_card ?? ""} />
      </fieldset>

      <p className="flex items-start gap-2 text-sm text-muted-foreground">
        <IconLockSimple className="mt-0.5 size-4 shrink-0" aria-hidden />
        {v.form.privacy}
      </p>
      {error && (
        <p role="alert" className="rounded-md bg-verdict-false-soft px-3 py-2.5 text-sm text-verdict-false-ink">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="lg" className="h-11" disabled={busy}>
          {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
          {busy ? v.form.sending : data.status === "none" ? v.form.send : v.form.resend}
        </Button>
        {onLater && (
          <Button type="button" variant="ghost" size="lg" className="h-11" onClick={onLater}>
            {v.form.later}
          </Button>
        )}
      </div>
    </form>
  );
}
