import Image from "next/image";
import Link from "next/link";
import { anton, specialElite } from "@/app/fonts/site";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";

// The doors into the app share the case file: the form on an index card, the night's pieces beside it
// (desktop only). The form itself is the app's, in the app's own colours.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  const frames = t.site.hero.frames;
  return (
    <div className={`site ${anton.variable} ${specialElite.variable}`}>
      <div className="dossier-auth">
        <main className="flex flex-col">
          <div className="flex items-center justify-between gap-4">
            <Link href="/" className="disp text-2xl tracking-[0.06em]">
              {brand.name}
            </Link>
            <span className="typed text-[15px] text-ink-soft">{t.site.status.open}</span>
          </div>
          <div className="flex w-full max-w-md flex-1 flex-col justify-center py-12">
            <div className="dossier-fiche" style={{ transform: "none" }}>
              <div data-ui className="rounded-md border border-border bg-card p-6 text-foreground sm:p-8">
                {children}
              </div>
            </div>
          </div>
          <p className="disp text-[clamp(28px,3vw,44px)] leading-none">{t.site.auth.tagline}</p>
        </main>
        <section className="side" aria-label={t.site.affaire.title}>
          {frames.map((f, i) => (
            <figure key={f.time} className="dossier-frame">
              <span className="tc tabular">{f.time}</span>
              <Image src={`/site/dossier/piece-${i + 1}.jpg`} alt={f.alt} width={900} height={600} sizes="28vw" priority={i === 0} />
              <figcaption>
                <span>{f.label}</span>
              </figcaption>
            </figure>
          ))}
          <span className="stamp" data-on="true" aria-hidden data-label={t.site.hero.stamp} />
        </section>
      </div>
    </div>
  );
}
