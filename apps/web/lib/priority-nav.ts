/**
 * Priority+ navigation: every tab stays in the bar while it fits; the rest folds into « Plus »
 * from the end. The first tab never folds. `widths` are the tabs' widths (gaps included), `room`
 * the width the island may take, `moreWidth` the width of the « Plus » button.
 * `activeFolded` tells the bar to give « Plus » the active tab's name and the indicator.
 */
export function foldTabs(widths: number[], room: number, moreWidth: number, active: number): { visible: number; activeFolded: boolean } {
  const total = widths.reduce((sum, w) => sum + w, 0);
  let visible = widths.length;
  if (total > room) {
    let used = moreWidth;
    visible = 0;
    while (visible < widths.length && used + widths[visible] <= room) used += widths[visible++];
    visible = Math.max(1, Math.min(visible, widths.length));
  }
  return { visible, activeFolded: active >= visible };
}
