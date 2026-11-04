/** AD-290: the layout of the Explore lens: callers left, callees right, unknown calls below. */
import { Link, Model, groupOf, links, moduleIndex, shortName } from "./model";
import type { UnknownRow } from "./api";

export const Side = { In: "in", Out: "out" } as const;
export type Side = (typeof Side)[keyof typeof Side];

/** A neighborhood folded into packages shows the functions of one package. */
export interface OpenGroup {
  readonly side: Side;
  readonly group: string;
}

export type LensItem =
  | { readonly kind: "node"; readonly symbol: number; readonly partial: boolean; readonly line: number }
  | { readonly kind: "group"; readonly group: string; readonly count: number }
  | { readonly kind: "back" }
  | { readonly kind: "text"; readonly text: string };

export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface PlacedItem extends Rect {
  readonly item: LensItem;
  readonly side: Side;
}

export interface Plate extends Rect {
  readonly module: number;
}

export interface LensLine {
  readonly path: string;
  readonly kind: "proven" | "claim" | "neutral" | "unknown";
}

export interface LensLayout {
  readonly width: number;
  readonly height: number;
  readonly heads: readonly { readonly text: string; readonly x: number; readonly y: number }[];
  readonly plates: readonly Plate[];
  readonly items: readonly PlacedItem[];
  readonly lines: readonly LensLine[];
  readonly center: Rect;
  readonly centerPlate: Plate;
  readonly siblings: Rect & { readonly shown: readonly number[]; readonly more: number };
  readonly unknown: readonly (Rect & { readonly row: UnknownRow })[];
}

const CARD_WIDTH = 236;
const CARD_HEIGHT = 54;
const CENTER_HEIGHT = 140;
const COLUMN_LEFT = 30;
const COLUMN_RIGHT = 676;
const CENTER_LEFT = 365;
const CENTER_WIDTH = 230;
const PAD = 16;
const FLAT_LIMIT = 10;
const NODES_SHOWN = 14;
const GROUPS_SHOWN = 8;
const SIBLINGS_SHOWN = 8;
const SIBLINGS_PER_ROW = 2;
const SIBLING_ROW = 27;
const UNKNOWN_SHOWN = 2;
const UNKNOWN_WIDTH = 196;
const UNKNOWN_HEIGHT = 50;
const RADIUS = 9;

interface Column {
  readonly items: readonly LensItem[];
  readonly head: string;
}

function column(model: Model, list: readonly Link[], side: Side, open: OpenGroup | null): Column {
  const name = side === Side.In ? "CALLED BY" : "CALLS";
  const node = (link: Link): LensItem => ({ kind: "node", symbol: link.other, partial: link.partial, line: link.line });
  if (open !== null && open.side === side) {
    const members = list.filter((link) => groupOf(model, link.other) === open.group);
    const items: LensItem[] = [{ kind: "back" }, ...members.slice(0, NODES_SHOWN).map(node)];
    if (members.length > NODES_SHOWN) {
      items.push({ kind: "text", text: `+${members.length - NODES_SHOWN} more in ${open.group}` });
    }
    return { items, head: `${name} · ${open.group} · ${members.length}` };
  }
  if (list.length > FLAT_LIMIT) {
    const counts = new Map<string, number>();
    for (const link of list) counts.set(groupOf(model, link.other), (counts.get(groupOf(model, link.other)) ?? 0) + 1);
    const groups = [...counts].sort((a, b) => b[1] - a[1]);
    const items: LensItem[] = groups.slice(0, GROUPS_SHOWN).map(([group, count]) => ({ kind: "group", group, count }));
    if (groups.length > GROUPS_SHOWN) {
      const rest = groups.slice(GROUPS_SHOWN).reduce((sum, [, count]) => sum + count, 0);
      items.push({ kind: "text", text: `+${groups.length - GROUPS_SHOWN} more groups (${rest})` });
    }
    return { items, head: `${name} · ${list.length} in ${groups.length} groups` };
  }
  const moduleName = (link: Link): string => model.graph.modules[moduleIndex(model, link.other)][0];
  const sorted = [...list].sort(
    (a, b) =>
      moduleName(a).localeCompare(moduleName(b)) ||
      Number(a.partial) - Number(b.partial) ||
      shortName(model, a.other).localeCompare(shortName(model, b.other)),
  );
  return { items: sorted.map(node), head: `${name} · ${list.length}` };
}

interface Row {
  readonly item: LensItem;
  readonly y: number;
  readonly module: number | null;
  readonly starts: boolean;
}

/** Cards of one module follow each other and share a plate; a plate has a label row. */
function arrange(model: Model, items: readonly LensItem[]): { rows: Row[]; height: number } {
  const rows: Row[] = [];
  let y = 0;
  let last: number | null = null;
  for (const item of items) {
    const module = item.kind === "node" ? moduleIndex(model, item.symbol) : null;
    const starts = module !== last;
    if (starts) {
      if (last !== null) y += 14;
      if (module !== null) y += 22;
      last = module;
    }
    rows.push({ item, y, module, starts });
    y += CARD_HEIGHT + 8;
  }
  return { rows, height: y };
}

/** A right angle with rounded corners, from a point of one card to a point of the center. */
function elbow(x1: number, y1: number, x2: number, y2: number, turn: number): string {
  const dy = y2 > y1 ? 1 : -1;
  if (Math.abs(y2 - y1) < 2 * RADIUS) return `M${x1} ${y1} H${x2}`;
  const before = turn - RADIUS * Math.sign(turn - x1);
  const after = turn + RADIUS * Math.sign(x2 - turn);
  const sy = y1 + dy * RADIUS;
  const ey = y2 - dy * RADIUS;
  return `M${x1} ${y1} H${before} Q${turn} ${y1} ${turn} ${sy} V${ey} Q${turn} ${y2} ${after} ${y2} H${x2}`;
}

export function layoutLens(model: Model, center: number, open: OpenGroup | null): LensLayout {
  const incoming = column(model, model.incoming[center], Side.In, open);
  const outgoing = column(model, model.outgoing[center], Side.Out, open);
  const left = arrange(model, incoming.items);
  const right = arrange(model, outgoing.items);
  const module = moduleIndex(model, center);
  const siblingList = model.members[module].filter((symbol) => symbol !== center);
  const shown = [...siblingList].sort((a, b) => links(model, b) - links(model, a)).slice(0, SIBLINGS_SHOWN);
  const siblingRows = Math.ceil(shown.length / SIBLINGS_PER_ROW);
  // The last row holds the count of the other functions of the module.
  const siblingHeight = (siblingRows + 1) * SIBLING_ROW + 6;
  const plateHeight = CENTER_HEIGHT + 12 + siblingHeight;
  const tallest = Math.max(left.height, right.height);
  // The columns hang on the middle of the center plate; the first column head sits PAD below the top.
  const top = PAD + 54 + Math.max((tallest - plateHeight) / 2, 0);
  const middle = top + plateHeight / 2;
  const columnTop = (height: number): number => middle - height / 2;
  const hub = top + CENTER_HEIGHT / 2;
  const centerX = CENTER_LEFT + CENTER_WIDTH / 2;

  const plates: Plate[] = [];
  const items: PlacedItem[] = [];
  const lines: LensLine[] = [];
  const place = (arranged: { rows: Row[]; height: number }, x: number, side: Side): void => {
    const start = columnTop(arranged.height);
    const drafts: { module: number; y0: number; y1: number }[] = [];
    for (const row of arranged.rows) {
      const y = start + row.y;
      if (row.module !== null) {
        if (row.starts) drafts.push({ module: row.module, y0: y - 22, y1: y + CARD_HEIGHT });
        else drafts[drafts.length - 1].y1 = y + CARD_HEIGHT;
      }
      items.push({ item: row.item, side, x, y, width: CARD_WIDTH, height: CARD_HEIGHT });
      if (row.item.kind === "node" || row.item.kind === "group") {
        const kind = row.item.kind === "group" ? "neutral" : row.item.partial ? "claim" : "proven";
        const mid = y + CARD_HEIGHT / 2;
        const path =
          side === Side.In
            ? elbow(x + CARD_WIDTH, mid, CENTER_LEFT, hub, CENTER_LEFT - 34)
            : elbow(CENTER_LEFT + CENTER_WIDTH, hub, x, mid, x - 34);
        lines.push({ path, kind });
      }
    }
    for (const draft of drafts) {
      const height = draft.y1 - draft.y0 + 14;
      plates.push({ module: draft.module, x: x - 10, y: draft.y0 - 6, width: CARD_WIDTH + 20, height });
    }
  };
  place(left, COLUMN_LEFT, Side.In);
  place(right, COLUMN_RIGHT, Side.Out);

  const unknownRows = model.unknown[center].slice(0, UNKNOWN_SHOWN);
  const unknownTop = top - 6 + plateHeight + 52;
  const turn = top - 6 + plateHeight + 26;
  const unknown = unknownRows.map((row, index) => {
    const x = unknownRows.length === 1 ? centerX - UNKNOWN_WIDTH / 2 : index > 0 ? centerX + 10 : centerX - UNKNOWN_WIDTH - 10;
    const target = x + UNKNOWN_WIDTH / 2;
    const dir = target > centerX ? 1 : -1;
    const from = top - 6 + plateHeight + 6;
    const path =
      Math.abs(target - centerX) < 2
        ? `M${centerX} ${from} V${unknownTop}`
        : `M${centerX} ${from} V${turn - RADIUS} Q${centerX} ${turn} ${centerX + dir * RADIUS} ${turn} H${target - dir * RADIUS} Q${target} ${turn} ${target} ${turn + RADIUS} V${unknownTop}`;
    lines.push({ path, kind: "unknown" });
    return { row, x, y: unknownTop, width: UNKNOWN_WIDTH, height: UNKNOWN_HEIGHT };
  });

  const bottom = Math.max(
    columnTop(left.height) + left.height,
    columnTop(right.height) + right.height,
    unknownTop + (unknown.length > 0 ? UNKNOWN_HEIGHT + 10 : 0),
    top - 6 + plateHeight + 30,
  );
  // Both heads sit above the tallest column, on one line.
  const headY = Math.min(columnTop(left.height), columnTop(right.height), top) - 34;
  return {
    width: COLUMN_RIGHT + CARD_WIDTH + COLUMN_LEFT,
    height: bottom + PAD * 2,
    heads: [
      { text: incoming.head, x: COLUMN_LEFT, y: headY },
      { text: outgoing.head, x: COLUMN_RIGHT, y: headY },
    ],
    plates,
    items,
    lines,
    center: { x: CENTER_LEFT, y: top, width: CENTER_WIDTH, height: CENTER_HEIGHT },
    centerPlate: {
      module,
      x: CENTER_LEFT - 12,
      y: top - 26,
      width: CENTER_WIDTH + 24,
      height: plateHeight + 26,
    },
    siblings: {
      x: CENTER_LEFT - 6,
      y: top + CENTER_HEIGHT + 4,
      width: CENTER_WIDTH + 12,
      height: siblingHeight,
      shown,
      more: Math.max(0, siblingList.length - SIBLINGS_SHOWN),
    },
    unknown,
  };
}
