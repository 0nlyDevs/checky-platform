import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Cormorant_Garamond } from "next/font/google";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { brand } from "@/lib/brand";
import "./globals.css";

// Everything: titles at 700-800 with tight tracking, text at 400-500, tabular figures in tables.
const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  subsets: ["latin", "latin-ext"],
  axes: ["opsz"],
});

// Verbatim quotations only (the verdict quote, source quotes) and the wordmark dot.
const cormorant = Cormorant_Garamond({
  variable: "--font-cormorant",
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
      <body className="min-h-full">
        <ThemeProvider>
          {children}
          <Toaster position="bottom-left" />
        </ThemeProvider>
      </body>
    </html>
  );
}
