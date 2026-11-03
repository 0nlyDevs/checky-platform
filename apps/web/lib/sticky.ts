/**
 * Where a sticky side column sticks, in px from the top of the viewport. It rides just under the
 * bar (`offset` + 16) while it fits; once taller than the screen the value turns negative so the
 * column's last block stays in view at the bottom (`margin` px above the edge).
 */
export function stickyTop(offset: number, viewport: number, column: number, margin = 24): number {
  return Math.min(offset + 16, viewport - column - margin);
}

/** A grid child's layout box: its left edge and its vertical extent, in px. */
export type Box = { left: number; top: number; bottom: number };

/**
 * Which child of a two-column grid should stick: the only child of the shorter column, as an
 * index into `boxes`. Children are grouped into columns by their left edge. Null when the grid
 * shows one column or more than two, when both columns are as tall (within 1 px), or when the
 * shorter column is made of several children (only a single element can stick).
 */
export function shorterColumn(boxes: Box[]): number | null {
  const columns = new Map<number, number[]>();
  boxes.forEach((b, i) => {
    const key = Math.round(b.left);
    columns.set(key, [...(columns.get(key) ?? []), i]);
  });
  if (columns.size !== 2) return null;
  const [a, b] = [...columns.values()].map((members) => ({
    members,
    height: Math.max(...members.map((i) => boxes[i].bottom)) - Math.min(...members.map((i) => boxes[i].top)),
  }));
  if (Math.abs(a.height - b.height) < 1) return null;
  const short = a.height < b.height ? a : b;
  return short.members.length === 1 ? short.members[0] : null;
}
