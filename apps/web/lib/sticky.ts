/**
 * Where a sticky side column sticks, in px from the top of the viewport. It rides just under the
 * bar (`offset` + 16) while it fits; once taller than the screen the value turns negative so the
 * column's last block stays in view at the bottom (`margin` px above the edge).
 */
export function stickyTop(offset: number, viewport: number, column: number, margin = 24): number {
  return Math.min(offset + 16, viewport - column - margin);
}
