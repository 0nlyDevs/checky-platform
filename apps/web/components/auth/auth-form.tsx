"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { IconCircleNotch, IconEye, IconEyeSlash } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { t } from "@/lib/i18n/fr";

type Mode = "signIn" | "signUp";

function errorMessage(code: string | undefined): string {
  const errors = t.auth.errors as Record<string, string>;
  return (code && errors[code]) || errors.generic;
}

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
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
      // Only follow same-site paths.
      router.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch {
      setError(t.auth.errors.network);
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <h1 className="page-title text-foreground">
        {isSignUp ? t.auth.signUpTitle : t.auth.signInTitle}
      </h1>
      <p className="mt-1.5 text-muted-foreground">{isSignUp ? t.auth.signUpLead : t.auth.signInLead}</p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate={false}>
        {isSignUp && (
          <div className="space-y-2">
            <Label htmlFor="name">{t.auth.name}</Label>
            <Input id="name" name="name" autoComplete="name" required className="h-11" />
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
            className="h-11"
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
              className="h-11 pr-12"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t.auth.hidePassword : t.auth.showPassword}
              aria-pressed={showPassword}
              aria-controls="password"
              className="absolute inset-y-0 right-1 my-auto inline-flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
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
          <p role="alert" className="rounded-md bg-verdict-false-soft px-3 py-2.5 text-sm text-verdict-false-ink">
            {error}
          </p>
        )}

        <Button type="submit" variant="action" size="xl" className="w-full" disabled={pending}>
          {pending && <IconCircleNotch className="animate-spin" aria-hidden />}
          {isSignUp ? t.auth.signUp : t.auth.signIn}
        </Button>
      </form>

      <p className="mt-8 text-sm text-muted-foreground">
        {isSignUp ? t.auth.toSignIn : t.auth.toSignUp}{" "}
        <Link
          href={`${isSignUp ? "/connexion" : "/inscription"}${next ? `?suite=${encodeURIComponent(next)}` : ""}`}
          className="font-medium text-foreground underline decoration-border hover:decoration-foreground"
        >
          {isSignUp ? t.auth.toSignInLink : t.auth.toSignUpLink}
        </Link>
      </p>
    </div>
  );
}
