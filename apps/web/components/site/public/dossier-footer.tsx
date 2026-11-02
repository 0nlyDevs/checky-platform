import Link from "next/link";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";
import credits from "@/public/site/credits.json";

/** The back of the folder: what this is, the hackathon, the photo credits, the name full width. */
export function DossierFooter({ photos = false }: { photos?: boolean }) {
  const s = t.site;
  return (
    <footer className="dossier-foot">
      <div className="cols">
        <p>{s.footer.what}</p>
        <p>{s.footer.made}</p>
        <nav aria-label={s.nav.label} className="flex flex-col">
          <Link href="/verifies" className="ulink">{s.pub.nav.verified}</Link>
          <Link href="/signaler" className="ulink">{s.pub.nav.report}</Link>
          <Link href="/connexion" className="ulink">{s.nav.signIn}</Link>
        </nav>
        {photos && (
          <p>
            {s.footer.fictional} {s.footer.photos}{" "}
            {credits.map((c, i) => (
              <span key={c.file}>
                <a href={c.page} className="ulink">
                  {c.credit}
                </a>
                {i < credits.length - 1 ? " · " : "."}
              </span>
            ))}
          </p>
        )}
      </div>
      <p className="big" aria-hidden>
        {brand.name}
      </p>
    </footer>
  );
}
