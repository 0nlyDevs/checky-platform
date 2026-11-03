// relire (mg) — machine-drafted Malagasy, not yet reread by a native speaker.
import type { look as fr } from "../fr/look";
import type { Part } from "./part";

export const look: Part<typeof fr> = {
  verifies: {
    hero: ["Efa *nohamarinina*", "ve?"],
    note: "Apetaho toy izao ihany",
    archive: "Ireo didy *farany*",
    reels: "Izay miely: ohatra noforonina",
    credits: "Horonan-tsary: Wikimedia Commons",
    reel: { market: "Eny an-tsena", outage: "Fahatapahan-jiro 72 ora?", sky: "Hita avy any ambony" },
    newsroom: "Mpanao gazety",
    allNewsrooms: "Ny mpanao gazety rehetra",
    seenOn: (where: string) => `Hita tao amin'ny ${where}`,
  },
  verdict: {
    seal: "Mpanao gazety nohamarinin'i Checky",
  },
};
