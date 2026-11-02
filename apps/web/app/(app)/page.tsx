"use client";

import type { Me, Workspace } from "@fanilo/shared";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR, { mutate as globalMutate } from "swr";
import { IconCircleNotch } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { RequestForm } from "@/components/verification/request-form";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";

// The landing's "Nommez votre rédaction" dialog leaves its choice here before sign-up.
const DRAFT = "fanilo:workspace";

function readDraft(): { name: string; demo: boolean } | null {
  try {
    const raw = typeof window === "undefined" ? null : sessionStorage.getItem(DRAFT);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function Onboarding() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft] = useState(readDraft);
  // Step 2: the newsroom exists and works privately; its verification request can wait.
  const [created, setCreated] = useState<{ id: string; name: string } | null>(null);

  // No newsroom yet: say why this screen comes first, once, as a toast.
  useEffect(() => {
    const id = toast(t.onboarding.nameFirst, { description: t.onboarding.nameFirstHint, id: "name-first" });
    return () => {
      toast.dismiss(id);
    };
  }, []);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setPending(true);
    setError(null);
    try {
      const ws = await api<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify({ name: String(form.get("name")) }),
      });
      if (form.get("demo")) await api(`/workspaces/${ws.id}/demo/reset`, { method: "POST" });
      try {
        sessionStorage.removeItem(DRAFT);
      } catch {
        // Storage may be unavailable; nothing to clean.
      }
      // /me is refreshed when leaving step 2: refreshing it now would send Home to the newsroom.
      toast.dismiss("name-first");
      setCreated({ id: ws.id, name: ws.name });
      setPending(false);
    } catch {
      setError(t.auth.errors.generic);
      setPending(false);
    }
  }

  if (created) {
    const go = () => {
      void globalMutate("/me");
      router.replace(`/w/${created.id}/rubrique`);
    };
    return (
      <div className="mx-auto max-w-2xl px-5 py-12 lg:py-16">
        <p className="text-sm font-bold text-muted-foreground">{t.verification.onboarding.step}</p>
        <h1 className="page-title mt-1 text-balance">{t.verification.onboarding.title}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t.verification.onboarding.lead}</p>
        <div className="mt-8">
          <RequestForm ws={created.id} outlet={created.name} onSent={go} onLater={go} />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg px-5 py-12 lg:py-20">
      <h1 className="page-title text-balance">{t.onboarding.title}</h1>
      <p className="mt-2 text-muted-foreground">{t.onboarding.lead}</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <div className="space-y-2">
          <Label htmlFor="ws-name">{t.onboarding.nameLabel}</Label>
          <Input
            id="ws-name"
            name="name"
            required
            maxLength={120}
            defaultValue={draft?.name}
            placeholder={t.onboarding.namePlaceholder}
            className="h-11"
          />
        </div>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" name="demo" defaultChecked={draft ? draft.demo : true} className="mt-0.5 size-4 accent-primary" />
          <span>
            <span className="font-medium">{t.common.demoData}</span>
            <span className="block text-muted-foreground">{t.onboarding.demoHint}</span>
          </span>
        </label>
        {error && (
          <p role="alert" className="rounded-md bg-verdict-false-soft px-3 py-2.5 text-sm text-verdict-false-ink">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" className="h-11" disabled={pending}>
          {pending && <IconCircleNotch className="animate-spin" aria-hidden />}
          {t.onboarding.create}
        </Button>
      </form>
    </div>
  );
}

function Home() {
  const router = useRouter();
  const wantsNew = useSearchParams().has("nouveau");
  const { data: me, error, mutate } = useSWR<Me>("/me", fetcher);
  const first = me?.memberships[0];

  useEffect(() => {
    if (first && !wantsNew) router.replace(`/w/${first.workspace_id}/rubrique`);
  }, [first, wantsNew, router]);

  if (error) {
    return (
      <div className="p-8">
        <p className="text-muted-foreground">{t.claims.errorTitle}</p>
        <Button variant="outline" className="mt-4" onClick={() => mutate()}>
          {t.claims.retry}
        </Button>
      </div>
    );
  }
  if (!me || (first && !wantsNew)) {
    return (
      <div className="space-y-6 p-5 lg:p-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }
  return <Onboarding />;
}

export default function HomePage() {
  return (
    <Suspense>
      <Home />
    </Suspense>
  );
}
