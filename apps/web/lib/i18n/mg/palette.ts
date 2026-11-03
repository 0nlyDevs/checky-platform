// relire (mg) — machine-drafted Malagasy, not yet reread by a native speaker.
import type { palette as fr } from "../fr/palette";
import type { Part } from "./part";

export const palette: Part<typeof fr> = {
  title: "Hikaroka na aiza na aiza",
  description: "Fizarana, dossier ary asa. Zana-tsipika hifidianana, Entrée hanokafana, Échap hanidiana.",
  placeholder: "Fizarana, dossier, na asa iray",
  list: "Valiny",
  groups: { spaces: "Fizarana", claims: "Dossier", actions: "Asa" },
  empty: "Tsy misy mifanaraka. Andramo « loharano », laharan'ny dossier iray, na « endrika ».",
  loading: "Mitady ireo dossier…",
  actions: { check: "Hamarino votoaty iray", ask: "Anontanio i Checky", theme: "Ovay ny endrika", shortcuts: "Hitsin-dalana amin'ny fitendry" },
  help: {
    title: "Hitsin-dalana amin'ny fitendry",
    description: "Tsy mandeha izy ireo raha manoratra ao anaty saha ianao.",
    close: "Hidio",
    rows: [
      { keys: ["Ctrl", "K"], label: "Hikaroka na aiza na aiza (⌘ K amin'ny Mac)" },
      { keys: ["/"], label: "Hikaroka na aiza na aiza" },
      { keys: ["V"], label: "Hamarino votoaty iray" },
      { keys: ["G", "D"], label: "Mankany amin'ireo dossier" },
      { keys: ["G", "S"], label: "Mankany amin'ireo loharano" },
      { keys: ["G", "E"], label: "Mankany amin'ny ekipa" },
      { keys: ["G", "P"], label: "Mankany amin'ny fikirakirana" },
      { keys: ["?"], label: "Asehoy ity fanampiana ity" },
      { keys: ["Échap"], label: "Hidio" },
    ],
  },
  undo: "Aoka ihany",
};
