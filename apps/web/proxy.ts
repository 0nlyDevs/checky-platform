import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

const AUTH_PAGES = ["/connexion", "/inscription"];

// Optimistic check on the cookie only; the app layout verifies the session for real.
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const signedIn = Boolean(getSessionCookie(request));
  const onAuthPage = AUTH_PAGES.includes(pathname);

  if (!signedIn && !onAuthPage) {
    const url = new URL("/connexion", request.url);
    if (pathname !== "/") url.searchParams.set("suite", pathname + search);
    return NextResponse.redirect(url);
  }
  if (signedIn && onAuthPage) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Skip API routes, Next internals and static files.
  matcher: ["/((?!api|_next/static|_next/image|icons/|icon.svg|apple-icon.png|logo.svg|manifest.webmanifest).*)"],
};
