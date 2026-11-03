// English for the command palette (mirrors fr/palette.ts). Machine-drafted, to be reread.
import type { palette as fr } from "../fr/palette";
import type { Part } from "../mg/part";

export const palette: Part<typeof fr> = {
  title: "Search everywhere",
  description: "Sections, cases and actions. Arrows to choose, Enter to open, Esc to close.",
  placeholder: "A section, a case, an action",
  list: "Results",
  groups: { spaces: "Sections", claims: "Cases", actions: "Actions" },
  empty: "Nothing matches. Try “sources”, a case reference or “theme”.",
  loading: "Searching cases…",
  actions: { check: "Check some content", ask: "Ask Checky", theme: "Change theme", shortcuts: "Keyboard shortcuts" },
  help: {
    title: "Keyboard shortcuts",
    description: "They're ignored while you type in a field.",
    close: "Close",
    rows: [
      { keys: ["Ctrl", "K"], label: "Search everywhere (⌘ K on Mac)" },
      { keys: ["/"], label: "Search everywhere" },
      { keys: ["V"], label: "Check some content" },
      { keys: ["G", "D"], label: "Go to cases" },
      { keys: ["G", "S"], label: "Go to sources" },
      { keys: ["G", "E"], label: "Go to the team" },
      { keys: ["G", "P"], label: "Go to settings" },
      { keys: ["?"], label: "Show this help" },
      { keys: ["Esc"], label: "Close" },
    ],
  },
  undo: "Undo",
  undoFailed: "Could not undo.",
  esc: "Esc",
  then: "then",
};
