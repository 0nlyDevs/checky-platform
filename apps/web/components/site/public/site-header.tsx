import Link from "next/link";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";

/** The folder's label strip, shared by every public page: the name, an optional status, the doors. */
export function SiteHeader({ status, anchors = false }: { status?: string; anchors?: boolean }) {
  const s = t.site;
  return (
    <header className="frame-x sticky top-0 z-20 flex items-center gap-7 bg-manila py-4">
      <Link href="/" className="disp text-2xl tracking-[0.06em]">
        {brand.name}
      </Link>
      {status && (
        <span id="case-status" className="typed text-[15px] text-ink-soft max-lg:hidden">
          {status}
        </span>
      )}
      <nav aria-label={s.nav.label} className="ml-auto flex gap-4 text-[15px] sm:gap-6">
        {anchors && (
          <a href="#methode" className="ulink max-lg:hidden">
            {s.nav.method}
          </a>
        )}
        <Link href="/verifies" className="ulink">
          {s.pub.nav.verified}
        </Link>
        <Link href="/signaler" className="ulink">
          <span className="sm:hidden">{s.pub.nav.reportShort}</span>
          <span className="max-sm:hidden">{s.pub.nav.report}</span>
        </Link>
        <Link href="/connexion" className="ulink">
          {s.nav.signIn}
        </Link>
      </nav>
    </header>
  );
}
