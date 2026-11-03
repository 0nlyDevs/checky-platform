"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { IconCircleNotch, IconEye, IconEyeSlash } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { clearApiToken } from "@/lib/api";
import { authClient } from "@/lib/auth-client";
import { t } from "@/lib/i18n/live";

type Mode = "signIn" | "signUp";

function errorMessage(code: string | undefined): string {
  const errors = t.auth.errors as Record<string, string>;
  return (code && errors[code]) || errors.generic;
}

export function AuthForm({ mode }: { mode: Mode }) {
  const next = useSearchParams().get("suite");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const isSignUp = mode === "signUp";

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    setPending(true);
    setError(null);
    try {
      const { error } = isSignUp
        ? await authClient.signUp.email({ email, password, name: String(form.get("name")) })
        : await authClient.signIn.email({ email, password });
      if (error) {
        setError(errorMessage(error.code));
        return;
      }
      // Only follow same-site paths. A full page load, not a client navigation: the previous
      // account's /me, newsrooms and API token stayed in memory, and a new account was sent into
      // the last user's newsroom (a 404 and an empty Ma rubrique).
      clearApiToken();
      window.location.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch {
      setError(t.auth.errors.network);
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      {isSignUp && (
        // Sign-up is the first of three steps: the newsroom and its verification follow at onboarding.
        <ol className="auth-steps" aria-label={t.look.auth.stepsLabel}>
          {t.look.auth.steps.map((step, i) => (
            <li key={step} aria-current={i === 0 ? "step" : undefined}>
              <span className="disc">{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      )}
      <h1 className="pub-h2 text-foreground">{isSignUp ? t.auth.signUpTitle : t.auth.signInTitle}</h1>
      <p className="mt-3 text-muted-foreground">{isSignUp ? t.auth.signUpLead : t.auth.signInLead}</p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate={false}>
        {isSignUp && (
          <div className="space-y-2">
            <Label htmlFor="name">{t.auth.name}</Label>
            <Input id="name" name="name" autoComplete="name" required className="h-12 rounded-full px-5" />
          </div>
        )}
        <div className="space-y-2">
          <Label htmlFor="email">{t.auth.email}</Label>
          <Input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            required
            className="h-12 rounded-full px-5"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">{t.auth.password}</Label>
          <div className="relative">
            <Input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete={isSignUp ? "new-password" : "current-password"}
              minLength={8}
              required
              aria-describedby={isSignUp ? "password-hint" : undefined}
              className="h-12 rounded-full pr-14 pl-5"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t.auth.hidePassword : t.auth.showPassword}
              aria-pressed={showPassword}
              aria-controls="password"
              className="absolute inset-y-0 right-1.5 my-auto inline-flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
            >
              {showPassword ? <IconEyeSlash aria-hidden /> : <IconEye aria-hidden />}
            </button>
          </div>
          {isSignUp && (
            <p id="password-hint" className="text-sm text-muted-foreground">
              {t.auth.passwordHint}
            </p>
          )}
        </div>

        {error && (
          <p role="alert" className="rounded-[16px] bg-verdict-false-soft px-4 py-3 text-sm text-verdict-false-ink">
            {error}
          </p>
        )}

        <Button type="submit" variant="action" size="xl" className="h-13 w-full rounded-full" disabled={pending}>
          {pending && <IconCircleNotch className="animate-spin" aria-hidden />}
          {isSignUp ? t.auth.signUp : t.auth.signIn}
        </Button>
      </form>

      <p className="mt-8 text-sm text-muted-foreground">
        {isSignUp ? t.auth.toSignIn : t.auth.toSignUp}{" "}
        <Link
          href={`${isSignUp ? "/sign-in" : "/sign-up"}${next ? `?suite=${encodeURIComponent(next)}` : ""}`}
          className="font-medium text-foreground underline decoration-border hover:decoration-foreground"
        >
          {isSignUp ? t.auth.toSignInLink : t.auth.toSignUpLink}
        </Link>
      </p>
    </div>
  );
}
