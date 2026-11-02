# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Journalist / reporter (primary).** Works in the field in Madagascar, often on a phone over slow or unstable mobile data. Receives claims as Facebook posts, WhatsApp forwards, screenshots and voice notes, in French and Malagasy. Job: check a claim fast and gather evidence they can cite.
- **Editor / fact-checker.** Desk role that reviews, assigns and validates verifications in a shared workspace and needs to see who did what.
- **Admin.** Team lead or demo operator: manages members and roles, resets demo data.
- **Jury (hackathon).** Judges a 3-minute live demo on 4 November 2026; needs it to load instantly and never fail.

## Product Purpose

Checky is a fact-checking and information-resilience tool for media professionals in Madagascar, born at the FANILO Hackathon (IFM and the French Embassy press service, Antananarivo, 2–4 November 2026). Journalists check claims, track their verification together, extract quotes from interviews, inspect images and share confirmed verdicts. Evidence, citations and verification progress stay together in the newsroom's workspace.

Success: a newsroom can take a rumour from its first appearance to a sourced, journalist-confirmed verdict, and the claim checker and verification board work end to end on seed data.

## Positioning

Built for the local newsroom reality: French and Malagasy content, field conditions on mobile data, and sources that arrive through Facebook and WhatsApp. Every AI output carries its evidence and citations, and a human journalist always confirms the verdict.

## Operating Context

- Mobile-first PWA installed on phones; also used on laptops at the desk.
- Shared workspaces with live updates: items, comments and job progress appear without refresh.
- Content types: pasted text, links, screenshots, photos, PDFs, audio interviews.
- The live demo runs on free tiers (Vercel, Render, Neon, free AI APIs) and must survive slow venue Wi-Fi.

## Capabilities and Constraints

- Stack: Next.js (App Router) web app with Better Auth; FastAPI API; Postgres; Socket.IO realtime; Postgres-backed job queue. See `docs/PRD.md`.
- UI language: French at launch; every string kept in one file so Malagasy can be added later. Content is French and Malagasy end to end.
- Roles: `admin`, `editor`, `journalist`, one per workspace member.
- Verdict scale is fixed: `true`, `misleading`, `false`, `unverifiable`. The app suggests; it never publishes a verdict on its own.
- Image signals are hints, never proof; the app does not claim to detect AI-generated images with certainty.
- Hackathon rules: every third-party component listed with version and license (`THIRD_PARTY.md`).
- Performance budget: first load under 3 s on 3G-like conditions; main-page JS under 250 KB gzipped.

## Brand Commitments

- Product name **Checky** (wordmark « Checky. » in Bricolage Grotesque 800, the dot in Cormorant Garamond italic), kept in one config file (`lib/brand.ts`) with one SVG logo so it changes in one place. A line « né au hackathon FANILO » may appear in footers and About only. Until the name slice lands, strings and the logo still read FANILO.
- Identity: ink and paper. Colour lives only on verdicts; see `DESIGN.md`.
- Voice: calm, factual, plain French; no hype. Verbatim quotations are set in Cormorant Garamond italic.

## Evidence on Hand

- `docs/PRD.md` (product requirements) and the hackathon rules PDF.
- No real users, testimonials, partner logos or usage figures exist; none may be invented. Demo content is seed data and must look like plausible public test data.

## Product Principles

1. The journalist decides: AI suggests with evidence; a person confirms every verdict.
2. Show the evidence: every answer cites its source and passage.
3. Works in the field: fast on a weak phone connection, recovers from drops.
4. One shared workflow: claims, evidence and confirmed verdicts stay connected.
5. Never fail in the demo: fallbacks over features.

## Accessibility & Inclusion

- WCAG AA contrast; keyboard navigable; every input labeled.
- Verdicts never rely on colour alone: always a label or icon.
- Readable on small, low-end Android phones from 360 px wide.
