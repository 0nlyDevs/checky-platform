# Checky implementation

Checky helps a newsroom research a claim, inspect its evidence, and decide what to publish. It retains the existing FastAPI/Next.js, AI gateway, pgvector RAG and public fact-check search. Content can concern any country; Madagascar is the first market, not a search restriction.

## Foundation

Migration `80f0950e8a14` adds the interrupted implementation's newsroom resource tables and workspace settings. The migration was generated against an isolated PostgreSQL 18 database and reviewed for additive changes. The reverse migration drops those new tables; do not downgrade a populated production database without a backup.

The graph runs parallel nodes with isolated input snapshots, individual timeouts, structured status events and bounded optional loops. Its checkpoint callback saves stage snapshots; it does **not** implement durable resume. Nodes that retrieve evidence can still return incomplete or unreliable material. They are not certified facts simply because they do not use an LLM.

Seal keys require an explicitly configured secret. The schema is preparation for later sealing and SMS features; it does not imply that those transports or cryptographic verification are implemented.
