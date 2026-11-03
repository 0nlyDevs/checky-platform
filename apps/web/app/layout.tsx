import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Cormorant_Garamond } from "next/font/google";
import { EcoProvider } from "@/components/prefs/eco";
import { ServiceWorker } from "@/components/pwa/service-worker";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { RippleListener } from "@/components/shell/ripple";
import { Toaster } from "@/components/ui/sonner";
import { brand } from "@/lib/brand";
import { PREFS_SCRIPT } from "@/lib/prefs-script";
import "./globals.css";

// Not preloaded: the faces download only when the page uses them, so Mode éco (system faces, see
// globals.css) never fetches them on a 2G or satellite link.
// Everything: titles at 700-800 with tight tracking, text at 400-500, tabular figures in tables.
const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  preload: false,
  subsets: ["latin", "latin-ext"],
  axes: ["opsz"],
});

// Verbatim quotations only (the verdict quote, source quotes) and the wordmark dot.
const cormorant = Cormorant_Garamond({
  variable: "--font-cormorant",
  preload: false,
  subsets: ["latin", "latin-ext"],
  weight: "500",
  style: "italic",
});

export const metadata: Metadata = {
  title: { default: brand.name, template: `%s · ${brand.name}` },
  description: brand.description,
  applicationName: brand.name,
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f2ee" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" suppressHydrationWarning className={`${bricolage.variable} ${cormorant.variable} h-full antialiased`}>
      <head>
        {/* Text size and Mode éco before the first paint (lib/prefs.ts). */}
        <script dangerouslySetInnerHTML={{ __html: PREFS_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <ThemeProvider>
          <EcoProvider>{children}</EcoProvider>
          <Toaster position="bottom-center" />
          <RippleListener />
          <ServiceWorker />
        </ThemeProvider>
      </body>
    </html>
  );
}
