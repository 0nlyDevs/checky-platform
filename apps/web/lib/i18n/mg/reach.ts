// relire (mg) — machine-drafted Malagasy, not yet reread by a native speaker.
import type { reach as fr } from "../fr/reach";
import type { Part } from "./part";

export const reach: Part<typeof fr> = {
  eco: {
    label: "Fomba mitsitsy",
    on: "Mandeha ny fomba mitsitsy",
    off: "Tsy mandeha ny fomba mitsitsy",
    hint: "Tsy dia mandany data sy bateria: ny soratra aloha, ny sary raha angatahina, tsy misy sary mihetsika, ny endri-tsoratry ny fitaovana.",
    savedData: "Mangataka ny hitsitsiana data ny navigateur-nao: nalefa ho azy ny fomba mitsitsy.",
    darkTip: "Amin'ny efijery OLED, mitsitsy bateria ihany koa ny endrika maizina.",
    darkAction: "Ampiasao ny endrika maizina",
    showImage: "Asehoy ny sary",
    imageHidden: "Nafenina ny sary amin'ny fomba mitsitsy",
    showMap: "Asehoy ny sarintany",
    mapHidden: "Nafenina ny sarintany amin'ny fomba mitsitsy",
    showVideo: "Ampidiro ny horonantsary",
    showAudio: "Ampidiro ilay hafatra am-peo", // relire (mg)
  },
  // relire (mg)
  lang: {
    label: "Fiteny",
    current: (name: string) => `Fiteny: ${name}`,
  },
  font: {
    label: "Haben'ny soratra",
    smaller: "Ahelezo ny soratra",
    larger: "Ahalehibeo ny soratra",
    reset: "Habe mahazatra",
    value: (percent: number) => `${percent.toLocaleString("fr-FR")} %`,
  },
};
