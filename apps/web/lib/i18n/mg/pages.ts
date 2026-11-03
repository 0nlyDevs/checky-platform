// relire (mg) — machine-drafted Malagasy, not yet reread by a native speaker.
// The not found and error pages (fr/pages.ts). Glossary: mg.ts.
import type { pages as fr } from "../fr/pages";
import type { Part } from "./part";

export const pages: Part<typeof fr> = {
  notFound: {
    title: "Tsy misy ity pejy ity",
    lead: "Mety tsy feno ny rohy, na nafindra toerana ilay pejy.",
    home: "Hiverina amin'ny fandraisana",
  },
  error: {
    title: "Nisy zavatra tsy nety",
    lead: "Tsy nety niseho ity pejy ity. Tsy very izay efa voatahirinao.",
    retry: "Andramo indray",
    home: "Hiverina amin'ny fandraisana",
    code: (digest: string) => `Kaodin'ny hadisoana: ${digest}`,
  },
};
