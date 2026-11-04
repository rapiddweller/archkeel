/** AD-290: routes the lines of a focused card through the gutters between cards; no segment crosses a card. Pure. */
import type { LevelBox, LevelLayout } from "./level-layout";

const CELL = 8;
const BEND = 6;
const NEAR = 2;
const RADIUS = 9;
const HEAD = 30;

type Point = readonly [number, number];

/** The boxes that a line must not cross: cards, stubs, tiles and the label strip of each plate. */
function obstaclesOf(layout: LevelLayout): LevelBox[] {
  return [
    ...layout.cards,
    ...layout.stubs,
    ...layout.tiles,
    ...layout.plates.map((plate) => ({ x: plate.x, y: plate.y, width: plate.width, height: HEAD - 6 })),
  ];
}

class Heap {
  private readonly items: { cost: number; state: number }[] = [];
  get size(): number {
    return this.items.length;
  }
  push(cost: number, state: number): void {
    const items = this.items;
    items.push({ cost, state });
    let at = items.length - 1;
    while (at > 0) {
      const parent = (at - 1) >> 1;
      if (items[parent].cost <= items[at].cost) break;
      [items[parent], items[at]] = [items[at], items[parent]];
      at = parent;
    }
  }
  pop(): { cost: number; state: number } {
    const items = this.items;
    const top = items[0];
    const last = items.pop() as { cost: number; state: number };
    if (items.length > 0) {
      items[0] = last;
      let at = 0;
      for (;;) {
        const left = 2 * at + 1;
        const right = left + 1;
        let least = at;
        if (left < items.length && items[left].cost < items[least].cost) least = left;
        if (right < items.length && items[right].cost < items[least].cost) least = right;
        if (least === at) break;
        [items[least], items[at]] = [items[at], items[least]];
        at = least;
      }
    }
    return top;
  }
}

const STEPS: readonly (readonly [number, number])[] = [
  [1, 0],
  [0, 1],
  [-1, 0],
  [0, -1],
];

/** A router over a grid of the layout; a cell that a card covers is blocked. */
export function makeRouter(layout: LevelLayout): (from: LevelBox, to: LevelBox) => Point[] | null {
  const columns = Math.ceil(layout.width / CELL) + 4;
  const rows = Math.ceil(layout.height / CELL) + 4;
  const blocked = new Uint8Array(columns * rows);
  const shift = 2;
  for (const box of obstaclesOf(layout)) {
    for (let row = Math.floor(box.y / CELL) + shift; row <= Math.floor((box.y + box.height - 0.01) / CELL) + shift; row += 1) {
      for (let column = Math.floor(box.x / CELL) + shift; column <= Math.floor((box.x + box.width - 0.01) / CELL) + shift; column += 1) {
        if (column >= 0 && column < columns && row >= 0 && row < rows) blocked[row * columns + column] = 1;
      }
    }
  }
  const near = new Uint8Array(columns * rows);
  for (let row = 1; row < rows - 1; row += 1) {
    for (let column = 1; column < columns - 1; column += 1) {
      const at = row * columns + column;
      if (blocked[at] === 0 && (blocked[at - 1] || blocked[at + 1] || blocked[at - columns] || blocked[at + columns])) near[at] = 1;
    }
  }
  const cellOf = (x: number, y: number): [number, number] => [Math.floor(x / CELL) + shift, Math.floor(y / CELL) + shift];
  /** The free cells next to a box. */
  const ring = (box: LevelBox): number[] => {
    const [c0, r0] = cellOf(box.x, box.y);
    const [c1, r1] = cellOf(box.x + box.width - 0.01, box.y + box.height - 0.01);
    const found: number[] = [];
    // Only cells whose centre faces the box: the line then meets the border at a right angle.
    const facesX = (column: number): boolean => {
      const x = (column - shift) * CELL + CELL / 2;
      return x >= box.x && x <= box.x + box.width;
    };
    const facesY = (row: number): boolean => {
      const y = (row - shift) * CELL + CELL / 2;
      return y >= box.y && y <= box.y + box.height;
    };
    for (let column = c0; column <= c1; column += 1) {
      if (!facesX(column)) continue;
      for (const row of [r0 - 1, r1 + 1]) found.push(row * columns + column);
    }
    for (let row = r0; row <= r1; row += 1) {
      if (!facesY(row)) continue;
      for (const column of [c0 - 1, c1 + 1]) found.push(row * columns + column);
    }
    return found.filter((at) => at >= 0 && at < columns * rows && blocked[at] === 0);
  };
  return (from, to) => {
    const starts = ring(from);
    const goals = new Set(ring(to));
    if (starts.length === 0 || goals.size === 0) return null;
    const best = new Float64Array(columns * rows * 4).fill(Infinity);
    const before = new Int32Array(columns * rows * 4).fill(-1);
    const [gx, gy] = cellOf(to.x + to.width / 2, to.y + to.height / 2);
    const guess = (at: number): number => Math.abs((at % columns) - gx) + Math.abs(Math.floor(at / columns) - gy);
    const heap = new Heap();
    for (const at of starts) {
      for (let direction = 0; direction < 4; direction += 1) {
        best[at * 4 + direction] = 0;
        heap.push(guess(at), at * 4 + direction);
      }
    }
    let end = -1;
    while (heap.size > 0) {
      const { state } = heap.pop();
      const at = state >> 2;
      const direction = state & 3;
      if (goals.has(at)) {
        end = state;
        break;
      }
      const cost = best[state];
      for (let turn = 0; turn < 4; turn += 1) {
        const [dx, dy] = STEPS[turn];
        const next = at + dy * columns + dx;
        const column = (at % columns) + dx;
        if (column < 1 || column >= columns - 1 || next < columns || next >= columns * (rows - 1) || blocked[next] === 1) continue;
        const step = cost + 1 + (near[next] ? NEAR : 0) + (turn === direction ? 0 : BEND);
        const key = next * 4 + turn;
        if (step < best[key]) {
          best[key] = step;
          before[key] = state;
          heap.push(step + guess(next), key);
        }
      }
    }
    if (end < 0) return null;
    const cells: number[] = [];
    for (let state = end; state >= 0; state = before[state]) cells.push(state >> 2);
    cells.reverse();
    const points: Point[] = cells.map((at) => [((at % columns) - shift) * CELL + CELL / 2, (Math.floor(at / columns) - shift) * CELL + CELL / 2]);
    return simplify([edge(from, points[0]), ...points, edge(to, points[points.length - 1])].filter(unique));
  };
}

const unique = (point: Point, index: number, all: readonly Point[]): boolean =>
  index === 0 || point[0] !== all[index - 1][0] || point[1] !== all[index - 1][1];

/** The point of the box border that a first or last cell faces. */
function edge(box: LevelBox, cell: Point): Point {
  const [x, y] = cell;
  if (y < box.y) return [x, box.y];
  if (y > box.y + box.height) return [x, box.y + box.height];
  return x < box.x ? [box.x, y] : [box.x + box.width, y];
}

/** Only the corners of a straight run. */
function simplify(points: readonly Point[]): Point[] {
  return points.filter((point, index) => {
    if (index === 0 || index === points.length - 1) return true;
    const [px, py] = points[index - 1];
    const [nx, ny] = points[index + 1];
    return !((px === point[0] && nx === point[0]) || (py === point[1] && ny === point[1]));
  });
}

/** A polyline with rounded corners, as an SVG path. */
export function roundedPath(points: readonly Point[]): string {
  if (points.length < 2) return "";
  let path = `M${points[0][0]} ${points[0][1]}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const [px, py] = points[index - 1];
    const [x, y] = points[index];
    const [nx, ny] = points[index + 1];
    const into = Math.min(RADIUS, Math.hypot(x - px, y - py) / 2);
    const out = Math.min(RADIUS, Math.hypot(nx - x, ny - y) / 2);
    const ax = x - Math.sign(x - px) * into;
    const ay = y - Math.sign(y - py) * into;
    const bx = x + Math.sign(nx - x) * out;
    const by = y + Math.sign(ny - y) * out;
    path += ` L${ax} ${ay} Q${x} ${y} ${bx} ${by}`;
  }
  const [lx, ly] = points[points.length - 1];
  return `${path} L${lx} ${ly}`;
}

/** The middle of a polyline and the angle of the segment there, in degrees; where an arrowhead of reduced motion sits. */
export function midOf(points: readonly Point[]): { x: number; y: number; angle: number } {
  const lengths = points.slice(1).map((point, index) => Math.hypot(point[0] - points[index][0], point[1] - points[index][1]));
  let left = lengths.reduce((sum, length) => sum + length, 0) / 2;
  for (let index = 0; index < lengths.length; index += 1) {
    if (left <= lengths[index] || index === lengths.length - 1) {
      const [x0, y0] = points[index];
      const [x1, y1] = points[index + 1];
      const share = lengths[index] === 0 ? 0 : left / lengths[index];
      return { x: x0 + (x1 - x0) * share, y: y0 + (y1 - y0) * share, angle: (Math.atan2(y1 - y0, x1 - x0) * 180) / Math.PI };
    }
    left -= lengths[index];
  }
  return { x: points[0][0], y: points[0][1], angle: 0 };
}
