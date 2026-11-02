/**
 * The theme switch: a diagonal slit through the centre draws across, holds a beat, then opens to
 * the whole screen (View Transitions, 1.5 s, --ease-theme). Instant without the API or under
 * reduced motion. A second press while it runs skips the running one.
 */

type Theme = "light" | "dark";
type Running = { skipTransition: () => void; ready: Promise<void>; finished: Promise<void> };
type WithTransitions = Document & { startViewTransition?: (update: () => void) => Running };

let running: Running | null = null;

const POINT = "polygon(50% 50%, 50% 50%, 50% 50%, 50% 50%)";
/** A band along the bottom-left to top-right diagonal, half-thickness d (in %). */
const D = (d: number) => `polygon(${-20 - d}% ${120 - d}%, ${120 - d}% ${-20 - d}%, ${120 + d}% ${-20 + d}%, ${-20 + d}% ${120 + d}%)`;

export function toggleThemeWithReveal(next: Theme, setTheme: (t: string) => void): void {
  const root = document.documentElement;
  const apply = () => {
    setTheme(next);
    // next-themes writes the class in an effect; the snapshot needs it now.
    root.classList.remove("light", "dark");
    root.classList.add(next);
    root.style.colorScheme = next;
  };
  if (running) {
    running.skipTransition();
    running = null;
  }
  const doc = document as WithTransitions;
  if (!doc.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    apply();
    return;
  }
  const vt = doc.startViewTransition(apply);
  running = vt;
  vt.ready
    .then(() => {
      root.animate(
        { clipPath: [POINT, D(0.5), D(1.2), D(110)], offset: [0, 0.4, 0.5, 1] },
        { duration: 1500, easing: getComputedStyle(root).getPropertyValue("--ease-theme").trim() || "cubic-bezier(.65,0,.35,1)", pseudoElement: "::view-transition-new(root)" },
      );
    })
    .catch(() => {});
  vt.finished.finally(() => {
    if (running === vt) running = null;
  });
}
