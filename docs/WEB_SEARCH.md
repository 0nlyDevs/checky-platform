# Dedicated web search

DuckDuckGo HTML/lite pages work from some networks but currently time out from the production
host. AI query preparation cannot repair an unavailable search engine. The backend now supports
Tavily's dedicated API so the search no longer needs to scrape those pages when a key is configured.

**The integration is not active until an operator supplies a key.** No account has been created,
no key has been invented and no paid plan or pay-as-you-go has been enabled by this change.

## Free-plan activation

1. Create your own account at [app.tavily.com](https://app.tavily.com). The documented Researcher
   plan provides 1,000 free API credits per month, without a credit card. **Do not add a card,
   subscribe to a paid plan or enable pay-as-you-go for this setup.**
2. Create an API key. Do not paste it in chat, commit it or put it in the browser extension.
3. In Render → `fanilo-api` → **Environment**, add:

   ```dotenv
   WEB_SEARCH_PROVIDER=tavily
   TAVILY_API_KEY=<your private key>
   ```

   Several free accounts add up: `TAVILY_API_KEY=key1,key2`. Keys are used in turn; each one's free
   usage is checked before its search, and a key that is exhausted, refused or rate limited is set
   aside (an hour, 30 s for a rate limit) so the next key answers. A refused key spends no credit, and
   a timeout or server error is never retried on another key.

4. Save and redeploy the existing service. Test the PARC passage again, and check that web-search
   attempts return results rather than timing out. Provider availability, relevance and coverage
   must be tested from production; local mocked tests are not a claim of successful activation.

For local development, the same variables belong in the gitignored `.env` file. With the default
`WEB_SEARCH_PROVIDER=auto`, a non-empty key selects Tavily; without a key it retains best-effort
DuckDuckGo. Explicit `tavily` selection without a key fails immediately and does not scrape HTML.

## Cost and credential safeguards

- Before each uncached search, `GET /usage` must verify a Researcher/free plan, a plan limit no
  higher than 1,000, remaining account/key allowance, and zero pay-as-you-go limit/usage.
  Unrecognized, missing or invalid usage information fails closed, before the search POST.
- The request explicitly sets `search_depth=basic` and `auto_parameters=false`. No advanced
  search upgrade, generated answer, raw page extraction or image search is requested.
- The documented basic search costs **one credit**. A public verification can use three web
  queries plus one fact-check query, so 1,000 credits are **not** 1,000 complete verifications.
  Result caching avoids repeat requests, and the existing per-IP/global public budgets still apply.
- Paid plans, enabled overage, exhausted quota, invalid keys and unavailable usage checks do not
  trigger a search. Failed search POSTs are not retried; an unknown response must not consume
  another credit automatically. API errors are not hidden behind slow HTML fallback attempts.
- Requests go only to the fixed HTTPS API origin, with certificate verification, a bearer token
  in the header, redirects disabled, timeouts and bounded JSON responses. Neither keys nor vendor
  error bodies are exposed to visitors. Raw provider scores are not presented as truth confidence.
- The application does not change the provider's billing settings. Keep the account free and
  overage disabled at the provider; the guards are not a substitute for that configuration.

Fact-check searches use explicit API domain filters for known fact-checkers, alongside the
existing optional Google Fact Check Tools results. Wikipedia remains a separate public API.
Search results are candidates, not verdicts; source reading and possible-republication warnings
remain in place. The visitor still needs no account and the extension needs no new permissions.

## References

- [Search REST API](https://docs.tavily.com/api-reference/endpoint/search)
- [Credits and pricing](https://docs.tavily.com/documentation/api-credits)
- [Rate limits](https://docs.tavily.com/documentation/rate-limits)
