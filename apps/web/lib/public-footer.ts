import { brand } from "./brand.ts";
import { ROUTES } from "../components/landing/content/site.ts";
import type { Messages } from "./i18n/live";

export const PUBLIC_FOOTER_STYLESHEET = "/site/public-footer.css";

type Copy = Pick<Messages, "site" | "publicLayer" | "registre" | "offline">;

const escape = (value: string) => value.replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);

/** One escaped, script-free footer for React pages and the low-bandwidth radio bulletin. */
export function publicFooterMarkup(t: Copy): { __html: string } {
  const f = t.site.footer;
  const link = (href: string, text: string) => `<li><a href="${escape(href)}">${escape(text)}</a></li>`;
  const section = (title: string, links: [string, string][]) => `<nav aria-label="${escape(title)}"><h3>${escape(title)}</h3><ul>${links.map(([href, text]) => link(href, text)).join("")}</ul></nav>`;
  const primary = (href: string, text: string, filled = false) => `<a class="pf-button${filled ? " pf-primary" : ""}" href="${escape(href)}">${escape(text)}${filled ? '<span aria-hidden="true">↗</span>' : ""}</a>`;
  const title = `${escape(f.call.first)}<br>${escape(f.call.before)}<em>${escape(f.call.emphasis)}</em>${escape(f.call.after)}`;
  return {
    __html: `<div class="pf-content"><h2 class="pf-title">${title}</h2><p class="pf-intro">${escape(f.intro)}</p><div class="pf-actions">${primary(ROUTES.signIn, f.open, true)}${primary(ROUTES.android, f.install)}${primary(ROUTES.verified, f.check)}</div><div class="pf-grid"><div><a class="pf-brand" href="/home">${escape(brand.name.toUpperCase())}</a><p>${escape(f.tagline)}</p></div>${section(f.product.title, [[ROUTES.android, f.product.android], ["/home#partout", f.product.extension], ["/home#partout", f.product.sms]])}${section(f.method.title, [["/home#verdict", f.method.verdicts], ["/home#preuve", f.method.evidence], ["/home#trajet", f.method.road]])}${section(f.cols.public, [[ROUTES.verified, t.site.pub.nav.check], [ROUTES.report, t.site.pub.nav.report], ["/official", t.registre.feed.title], ["/scanner", t.offline.scanner.title], ["/flashes", t.publicLayer.footer.flashs], [ROUTES.signUp, t.site.home.newsroomsCta]])}</div><div class="pf-legal"><span>${escape(f.copyright)}</span><span>${escape(f.location)}</span><a href="/site/landing/videos/CREDITS.md" target="_blank" rel="noreferrer">${escape(f.credits)}</a></div><p class="pf-disclaimer">${escape(f.fictional)}</p></div><div class="pf-wordmark" aria-hidden="true"><svg viewBox="0 0 1000 245" focusable="false"><defs><linearGradient id="public-footer-glow" x1="0" y1="0" x2="0" y2="1"><stop offset="35%" stop-color="white" stop-opacity="0"/><stop offset="70%" stop-color="white" stop-opacity="0.3"/><stop offset="100%" stop-color="white"/></linearGradient></defs><text x="0" y="232" textLength="1000" lengthAdjust="spacingAndGlyphs">${escape(brand.name.toUpperCase())}</text><text class="pf-bloom" x="0" y="232" textLength="1000" lengthAdjust="spacingAndGlyphs">${escape(brand.name.toUpperCase())}</text></svg></div>`,
  };
}

/** The standalone bulletin bypasses React layouts; keep exactly the same footer there. */
export function publicFooterHtml(t: Copy): string {
  return `<footer id="fin" class="public-footer" role="contentinfo">${publicFooterMarkup(t).__html}</footer>`;
}
