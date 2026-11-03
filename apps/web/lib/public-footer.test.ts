import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { publicFooterHtml, publicFooterMarkup, PUBLIC_FOOTER_STYLESHEET } from "./public-footer.ts";
import { loadTestMessages } from "./test-i18n-loader.ts";

const dictionaries = await loadTestMessages();

test("the landing and standalone bulletin use identical escaped footer content", () => {
  const html = publicFooterHtml(dictionaries.fr);
  assert.ok(html.includes(publicFooterMarkup(dictionaries.fr).__html));
  for (const href of ["/sign-in", "/sign-up", "/verdicts", "/report", "/official", "/scanner", "/flashes", "/home#partout", "/home#verdict", "/home#preuve", "/home#trajet"]) {
    assert.ok(html.includes(`href="${href}"`), href);
  }
  assert.ok(html.indexOf('class="pf-legal"') < html.indexOf('class="pf-wordmark"'));
  assert.match(html, /<\/svg><\/div><\/footer>$/);
  assert.doesNotMatch(html, /<script|data-reveal|href="#/i);
});

test("all three languages translate the same footer", () => {
  for (const t of Object.values(dictionaries)) {
    const html = publicFooterHtml(t);
    assert.ok(html.includes(t.site.footer.open));
    assert.ok(html.includes(t.site.footer.credits));
  }
});

test("translated content is text, never executable HTML", () => {
  const base = dictionaries.fr;
  const t = { ...base, site: { ...base.site, footer: { ...base.site.footer, intro: '<img src=x onerror="alert(1)">' } } };
  const html = publicFooterHtml(t);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});

test("one scoped stylesheet supplies the full-width glow and print fallback", () => {
  const css = readFileSync(new URL(`../public${PUBLIC_FOOTER_STYLESHEET}`, import.meta.url), "utf8");
  assert.match(css, /\.pf-wordmark[^}]*width: 100%/);
  assert.match(css, /drop-shadow/);
  assert.match(css, /backdrop-filter: blur/);
  assert.match(css, /@media print/);
});
