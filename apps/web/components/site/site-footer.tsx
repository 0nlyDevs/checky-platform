"use client";

import { useT } from "@/lib/i18n";
import { publicFooterMarkup } from "@/lib/public-footer";
import "@/public/site/public-footer.css";

/** Shared with the landing, public pages, auth doors and script-free radio bulletin. */
export function SiteFooter() {
  const html = publicFooterMarkup(useT());
  // Only the escaped application-owned template is accepted here; never pass API or user HTML.
  return <footer id="fin" className="public-footer" role="contentinfo" dangerouslySetInnerHTML={html} />;
}
