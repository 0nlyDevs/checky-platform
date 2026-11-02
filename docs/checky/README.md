# Checky implementation

Checky helps a newsroom research a claim, inspect its evidence, and decide what to publish. It retains the existing FastAPI/Next.js, AI gateway, pgvector RAG and public fact-check search. Content can concern any country; Madagascar is the first market, not a search restriction.

## Foundation

Migration `80f0950e8a14` adds the interrupted implementation's newsroom resource tables and workspace settings. The migration was generated against an isolated PostgreSQL 18 database and reviewed for additive changes. The reverse migration drops those new tables; do not downgrade a populated production database without a backup.

The graph runs parallel nodes with isolated input snapshots, individual timeouts, structured status events and bounded optional loops. Its checkpoint callback saves stage snapshots; it does **not** implement durable resume. Nodes that retrieve evidence can still return incomplete or unreliable material. They are not certified facts simply because they do not use an LLM.

Seal keys require an explicitly configured secret. The schema is preparation for later sealing and SMS features; it does not imply that those transports or cryptographic verification are implemented.

## Implemented workflow

A journalist pastes or shares text, a link or an uploaded source. `POST /workspaces/{ws}/crew` streams the research steps and returns searched pages, passages from the newsroom's RAG archive, comparison against curated originals, possible framing signals, a suggested reading and a critic's objections. A source search result is marked as a snippet until the underlying page is read. The graph skips the synthesis when it has no readable passages. The no-AI switch still searches and compares. Critic findings must quote a passage actually read.

The percentage on the research panel is **documentation completeness**, not probability of truth: pages read (25 points), passages cited (25), dated pages (25), distinct hosts (25). The panel shows each component, dates, unread sources and possible copied text. Different hosts do not establish source independence. Framing and political signals quote the submitted text and never affect the percentage or the suggested verdict. Publisher ownership, correction policy and political leaning are explicitly unassessed. This borrows the transparency and per-signal explanations that make products such as NewsGuard and evidence-based browser extensions useful, without copying their proprietary ratings or claiming a validated accuracy score.

Contacts, original notices, dated statistics, radio observations and personal beat filters have API routes and simple web pages. The original registry performs text matching and differences; it does not authenticate an issuer yet. Radio observations are written by a human and can reference an audio or video source already uploaded to the newsroom. Automated radio capture and Malagasy speech recognition are not part of this implementation.

A journalist can sign a verdict with a public explanation. With double signature enabled, a different editor must publish the exact signed version. Protected signature fields cannot be supplied through generic item writes. Public verdicts come from published newsroom dossiers; the public evidence search remains available independently. A route log records only observations someone actually entered, and the radio, SMS and social formats are drafts for copying. No SMS gateway, partner-radio receipt or automatic reach measurement exists yet.

## Demo pitch, 3 minutes

Open on one disputed video or notice. Say: “A newsroom needs an answer it can cite, while the claim keeps travelling through social media and radio.” Paste it into Checky. The live trace shows public sources, the newsroom archive and the original registry working together. Open “Pourquoi ce résultat ?”: point to the passages read, their dates, missing information and the critic's objection. Explain the percentage precisely: it measures how much of this research is documented; it does not pronounce the claim true. If the article uses a charged political phrase, show the literal quote in “Cadrage”; explain that tone alone does not make a claim false.

Then open “Qui peut le prouver ?” and show the relevant office, its declared official page and professional contact. If the newsroom chooses to publish, sign the explanation; an editor releases it if the newsroom requires two signatures. Prepare the radio line and the social message from the published verdict, and record where the correction actually went. Close with the public answer: people can consult sources immediately, and a newsroom's published verdict carries its name.

Positioning: a chain of evidence and responsibility that travels from the journalist's source search to the channel where the claim circulated. The research graph and the newsroom roles serve this one chain. This is a working editorial workflow, not a promise of an autonomous AI journalist. Viability depends on newsroom adoption, curated contacts and originals, reliable source access and later distribution partners. A future revenue pilot can charge institutions for managed original notices and alerts while keeping verification free for newsrooms and the public; no customer or revenue is claimed yet.

## Remaining product work

The original Claude artifact and mockup have no connected document session in this workspace, so this repository note is the reviewable record for this implementation. Mobile branding and its new research screen, verified institutional seals, automatic source monitoring, outbound radio partnerships, offline registry sync and an SMS gateway require separate implementations and field testing. Do not demo these as working.
