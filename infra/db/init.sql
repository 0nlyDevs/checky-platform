-- Better Auth tables live in "auth", our tables in "app" (see docs/PRD.md, Data model).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS app;
