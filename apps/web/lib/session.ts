import "server-only";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";

export type SessionUser = { id: string; name: string; email: string };

/** The signed-in user, or a redirect that clears a stale cookie then signs in. Cached per browser session. */
export async function getCurrentUser(): Promise<SessionUser> {
  "use cache: private";
  const session = await auth.api.getSession({ headers: await headers() });
  // Not straight to /sign-in: a stale cookie would bounce between it and `/` (see the route).
  if (!session) redirect("/api/session/clear");
  const { id, name, email } = session.user;
  return { id, name, email };
}
