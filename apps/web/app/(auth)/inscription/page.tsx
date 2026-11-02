import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm } from "@/components/auth/auth-form";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = { title: t.auth.signUpTitle };

export default function SignUpPage() {
  return (
    <Suspense>
      <AuthForm mode="signUp" />
    </Suspense>
  );
}
