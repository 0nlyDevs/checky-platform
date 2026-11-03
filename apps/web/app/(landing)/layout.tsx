import { Cormorant_Garamond, JetBrains_Mono } from "next/font/google";

// The landing's own type on top of the root layout's Bricolage: the italic accent at 500 and 600,
// and the mono of its figures and labels.
const serif = Cormorant_Garamond({
  variable: "--font-landing-serif",
  subsets: ["latin", "latin-ext"],
  weight: ["500", "600"],
  style: "italic",
});
const mono = JetBrains_Mono({ variable: "--font-landing-mono", subsets: ["latin", "latin-ext"] });

// The landing brings its own chrome (ruler, wordmark, footer), so no site bar here.
export default function LandingLayout({ children }: LayoutProps<"/">) {
  return <div className={`${serif.variable} ${mono.variable}`}>{children}</div>;
}
