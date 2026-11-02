import { betterAuth } from "better-auth";
import { jwt } from "better-auth/plugins";
import { nextCookies } from "better-auth/next-js";
import { Pool } from "pg";

const baseURL = process.env.BETTER_AUTH_URL ?? "http://localhost:3000";

export const auth = betterAuth({
  baseURL,
  // Better Auth owns the `better_auth` schema (Supabase reserves `auth`); app tables live in `app` (managed by Alembic).
  database: new Pool({
    connectionString: process.env.DATABASE_URL,
    options: "-c search_path=better_auth",
  }),
  emailAndPassword: { enabled: true },
  plugins: [
    // FastAPI verifies these against /api/auth/jwks; issuer and audience must match its AUTH_* env.
    jwt({ jwt: { issuer: baseURL, audience: baseURL, expirationTime: "15m" } }),
    nextCookies(),
  ],
});
