// The public pages' titles and the words of their new pieces. A title is a list of lines; the word
// between asterisks is set in the landing's italic (components/site/public/kit.tsx, `Em`).
export const look = {
  verifies: {
    hero: ["Est-ce déjà", "*vérifié* ?"],
    note: "Collez-le tel quel",
    archive: "Les derniers *verdicts*",
    reels: "Ce qui circule : exemples fictifs",
    credits: "Vidéos : Wikimedia Commons",
    reel: { market: "Au marché", outage: "72 h de délestage ?", sky: "Vu du ciel" },
    newsroom: "Rédaction",
    allNewsrooms: "Toutes les rédactions",
    seenOn: (where: string) => `Vu sur ${where}`,
  },
  report: { hero: ["Signaler", "une *rumeur*"], note: "Tel quel, fautes comprises" },
  follow: { hero: ["Suivi du", "*signalement*"] },
  reponse: { hero: ["Une rédaction vous", "pose une *question*"] },
  verdict: {
    seal: "Rédaction vérifiée par Checky",
  },
};
