import { toast } from "sonner";
import { palette } from "@/lib/i18n/fr/palette";

export const UNDO_MS = 6000;

/**
 * A reversible act, already done: the toast says so and offers « Annuler » for 6 s (the bar shows
 * the time left). `onUndo` puts things back; `after` is a short confirmation printed once undone.
 * Acts with no undo keep their confirmation dialog instead.
 */
export function undoable(message: string, onUndo: () => Promise<unknown> | unknown, after?: string) {
  toast.success(message, {
    duration: UNDO_MS,
    className: "undo-toast",
    action: {
      label: palette.undo,
      onClick: async () => {
        try {
          await onUndo();
          if (after) toast(after);
        } catch {
          toast.error("Impossible d'annuler.");
        }
      },
    },
  });
}
