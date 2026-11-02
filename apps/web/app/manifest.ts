import type { MetadataRoute } from "next";
import { brand } from "@/lib/brand";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${brand.name} — ${brand.tagline}`,
    short_name: brand.name,
    description: brand.description,
    lang: "fr",
    start_url: "/",
    display: "standalone",
    background_color: "#f4f6f5",
    theme_color: "#0f3b36",
    icons: [{ src: "/logo.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
