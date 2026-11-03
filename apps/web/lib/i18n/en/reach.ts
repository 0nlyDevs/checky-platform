// English for the reach slice (mirrors fr/reach.ts). Machine-drafted, to be reread.
// Reading preferences: Data saver and the text size.
import type { Overrides } from "../index";

export const reach: NonNullable<Overrides["reach"]> = {
  eco: {
    label: "Data saver",
    on: "Data saver on",
    off: "Data saver off",
    hint: "Less data and less battery: text first, images on demand, no animation, system fonts.",
    savedData: "Your browser asks to save data: Data saver is on.",
    darkTip: "On an OLED screen, the dark theme also saves battery.",
    darkAction: "Switch to dark",
    showImage: "Show the image",
    imageHidden: "Image hidden by Data saver",
    showMap: "Show the map",
    mapHidden: "Map hidden by Data saver",
    showVideo: "Load the video",
    showAudio: "Load the voice note",
  },
  lang: {
    label: "Language",
    current: (name: string) => `Language: ${name}`,
  },
  font: {
    label: "Text size",
    smaller: "Smaller text",
    larger: "Larger text",
    reset: "Normal size",
    value: (percent: number) => `${percent.toLocaleString("en-GB")}%`,
  },
};
