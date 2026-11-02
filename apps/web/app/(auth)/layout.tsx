import { Wordmark } from "@/components/brand/logo";
import { brand } from "@/lib/brand";

const LANES = [
  { from: 4, to: 62, tone: "bg-verdict-true" },
  { from: 18, to: 88, tone: "bg-verdict-misleading" },
  { from: 30, to: 88, tone: "border border-sidebar-foreground/60" },
  { from: 9, to: 48, tone: "bg-verdict-false" },
  { from: 52, to: 88, tone: "bg-verdict-unverifiable" },
];

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex">
        <Wordmark />
        {/* The programme grid, as a quiet promise of what is inside. */}
        <div aria-hidden className="relative my-12">
          <div className="mb-3 flex justify-between font-display text-sm tracking-wide text-sidebar-muted tabular">
            {["06h", "09h", "12h", "15h", "18h", "21h"].map((h) => (
              <span key={h}>{h}</span>
            ))}
          </div>
          <div className="relative space-y-3">
            {LANES.map((l, i) => (
              <div key={i} className="relative h-7 border-t border-sidebar-border">
                <div
                  className={`absolute top-1.5 h-5 rounded-sm ${l.tone}`}
                  style={{ left: `${l.from}%`, width: `${l.to - l.from}%` }}
                />
              </div>
            ))}
            <div className="absolute -top-2 bottom-0 w-0.5 bg-signal" style={{ left: "88%" }} />
          </div>
        </div>
        <div className="max-w-md">
          <p className="text-2xl font-semibold leading-snug text-balance">
            Voir ce qui circule, depuis quand, et ce qui est vérifié.
          </p>
          <p className="mt-3 text-sidebar-muted">{brand.description}</p>
        </div>
      </aside>
      <main className="flex flex-col px-5 py-8 sm:px-10">
        <Wordmark className="lg:hidden" />
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">{children}</div>
      </main>
    </div>
  );
}
