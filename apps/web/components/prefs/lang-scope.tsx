"use client";

import { Fragment } from "react";
import { useDocumentLang, useLang } from "@/lib/i18n";

/**
 * Remounts its subtree when the language changes, so every component reading the live `t` from
 * `@/lib/i18n` re-renders in the new language (the desk and the auth pages). `<html lang>` follows.
 */
export function LangScope({ children }: { children: React.ReactNode }) {
  const lang = useLang();
  useDocumentLang();
  return <Fragment key={lang}>{children}</Fragment>;
}
