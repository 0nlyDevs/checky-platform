import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

const AUTH_PAGES = ["/connexion", "/inscription"];
// Open to everyone, signed in or not: the landing and the public verdicts, tips and their follow-up.
const PUBLIC_PAGES = ["/accueil", "/verifies", "/signaler", "/suivi"];
const isPublic = (path: string) => PUBLIC_PAGES.some((p) => path === p || path.startsWith(`${p}/`));

// Optimistic check on the cookie only; the app layout verifies the session for real.
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const signedIn = Boolean(getSessionCookie(request));
  const onAuthPage = AUTH_PAGES.includes(pathname);

  // Signed-out visitors see the landing at the root.
  if (!signedIn && pathname === "/") return NextResponse.rewrite(new URL("/accueil", request.url));
  if (isPublic(pathname)) return NextResponse.next();
  if (!signedIn && !onAuthPage) {
    const url = new URL("/connexion", request.url);
    url.searchParams.set("suite", pathname + search);
    return NextResponse.redirect(url);
  }
  if (signedIn && onAuthPage) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Skip API routes, Next internals and static files.
  matcher: ["/((?!api|_next/static|_next/image|icons/|site/|icon.svg|apple-icon.png|logo.svg|manifest.webmanifest).*)"],
};
