// Reading preferences: Mode éco and the text size.
export const reach = {
  eco: {
    label: "Mode éco",
    on: "Mode éco activé",
    off: "Mode éco désactivé",
    hint: "Moins de données et moins de batterie : texte d'abord, images à la demande, pas d'animation, polices du système.",
    savedData: "Votre navigateur demande d'économiser les données : le mode éco est activé.",
    darkTip: "Sur un écran OLED, le thème sombre économise aussi la batterie.",
    darkAction: "Passer en sombre",
    showImage: "Afficher l'image",
    imageHidden: "Image masquée en mode éco",
    showMap: "Afficher la carte",
    mapHidden: "Carte masquée en mode éco",
    showVideo: "Charger la vidéo",
    showAudio: "Charger la note vocale",
  },
  // The interface language (the desk's user menu and the preference dock).
  lang: {
    label: "Langue",
    current: (name: string) => `Langue : ${name}`,
  },
  font: {
    label: "Taille du texte",
    smaller: "Réduire le texte",
    larger: "Agrandir le texte",
    reset: "Taille normale",
    value: (percent: number) => `${percent.toLocaleString("fr-FR")} %`,
  },
} as const;
