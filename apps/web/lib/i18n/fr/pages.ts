// Checky strings for the pages Next.js shows by itself: not found and an unexpected error.

export const pages = {
  notFound: {
    title: "Cette page n'existe pas",
    lead: "Le lien est peut-être incomplet, ou la page a été déplacée.",
    home: "Revenir à l'accueil",
  },
  error: {
    title: "Quelque chose n'a pas marché",
    lead: "Cette page n'a pas pu s'afficher. Rien de ce que vous aviez enregistré n'est perdu.",
    retry: "Réessayer",
    home: "Revenir à l'accueil",
    code: (digest: string) => `Code de l'erreur : ${digest}`,
  },
} as const;
