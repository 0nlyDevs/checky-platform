import { betterAuth } from "better-auth";
import { jwt } from "better-auth/plugins";
import { nextCookies } from "better-auth/next-js";
import { expo } from "@better-auth/expo";
import { Pool } from "pg";

const baseURL = process.env.BETTER_AUTH_URL ?? "http://localhost:3000";

export const auth = betterAuth({
  baseURL,
  // Better Auth owns the `better_auth` schema; app tables live in `app` (managed by Alembic).
  database: new Pool({
    connectionString: process.env.DATABASE_URL,
    options: "-c search_path=better_auth",
  }),
  emailAndPassword: { enabled: true },
  // The Checky phone app (scheme `fanilo`); Expo's dev client also signs in from `exp://` in development.
  trustedOrigins: ["fanilo://", ...(process.env.NODE_ENV === "production" ? [] : ["exp://**"])],
  plugins: [
    // FastAPI verifies these against /api/auth/jwks; issuer and audience must match its AUTH_* env.
    jwt({ jwt: { issuer: baseURL, audience: baseURL, expirationTime: "15m" } }),
    // Lets the phone app sign in with its own cookie store (SecureStore) and the `expo-origin` header.
    expo(),
    nextCookies(),
  ],
});
