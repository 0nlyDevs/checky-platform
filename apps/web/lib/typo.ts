/** French typesetting for text that comes from the newsroom: a figure keeps its unit, « keeps its words. */
export function tidy(text: string) {
  return text
    .replace(/(\d)\s+(?=(h|min|j|%|ar|ariary|km|mm|ans?)\b)/gi, "$1 ")
    .replace(/\s+([?!:;»])/g, " $1")
    .replace(/«\s+/g, "« ");
}
