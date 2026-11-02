import { NextResponse, type NextRequest } from "next/server";

/**
 * A session cookie whose session no longer exists (expired, signed out elsewhere, database reset)
 * would make proxy.ts and the app layout bounce between `/` and `/connexion` forever. The layout
 * sends such visitors here instead: drop every Better Auth cookie, then go to sign-in.
 * Under /api, so proxy.ts never sees this route.
 */
export function GET(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/connexion", request.url));
  for (const { name } of request.cookies.getAll()) {
    if (name.startsWith("better-auth.") || name.startsWith("__Secure-better-auth.")) {
      response.cookies.delete(name);
    }
  }
  return response;
}
