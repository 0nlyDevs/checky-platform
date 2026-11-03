// English for the public pages' titles (mirrors fr/look.ts).
import type { Overrides } from "../index";

export const look: NonNullable<Overrides["look"]> = {
  verifies: {
    hero: ["Already", "*checked*?"],
    note: "Paste it as it is",
    archive: "The latest *verdicts*",
    reels: "What circulates: fictional examples",
    credits: "Videos: Wikimedia Commons",
    reel: { market: "At the market", outage: "72 hours of power cuts?", sky: "Seen from the sky" },
    newsroom: "Newsroom",
    allNewsrooms: "All newsrooms",
    seenOn: (where: string) => `Seen on ${where}`,
  },
  verdict: {
    seal: "Newsroom verified by Checky",
  },
};
