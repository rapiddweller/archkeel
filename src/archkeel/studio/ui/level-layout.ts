/** AD-290: the layouts of the levels below the Map: the modules of a component, the functions of a module. Pure. */
import { Side } from "./lens-layout";
import { Level, Model, Tally } from "./model";

export const LEVEL_CARD = { width: 220, height: 66, gap: 12 } as const;
export const LEVEL_STUB = { width: 210, height: 58, gap: 12 } as const;
const HEAD = 26;
const SPREAD = 110;
const STUBS_SHOWN = 12;
const FUNCTIONS_SHOWN = 60;
const LINES_SHOWN = 160;
const WIDE = 18;

export interface LevelBox {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}
export interface LevelCard extends LevelBox {
  /** The module or the function. */
  readonly index: number;
}
export interface LevelPlate extends LevelBox {
  readonly label: string;
}
/** Another component (above the modules) or another module (above the functions) that calls in or is called. */
export interface LevelStub extends LevelBox, Tally {
  readonly side: Side;
  readonly id: number;
}
export interface LevelLine extends Tally {
  readonly path: string;
  readonly width: number;
  readonly strong: boolean;
  readonly a: string;
  readonly b: string;
  readonly middle: readonly [number, number];
}
export interface LevelLayout {
  readonly width: number;
  readonly height: number;
  readonly plates: readonly LevelPlate[];
  readonly cards: readonly LevelCard[];
  readonly stubs: readonly LevelStub[];
  readonly lines: readonly LevelLine[];
  /** Stubs and functions that did not fit the drawing, counted. */
  readonly more: { readonly stubs: number; readonly cards: number };
}

interface Group {
  readonly label: string;
  readonly items: readonly number[];
}
interface RawStub extends Tally {
  readonly id: number;
}
interface RawLine extends Tally {
  readonly a: string;
  readonly b: string;
}
interface Sites {
  readonly proven: Set<number>;
  readonly claim: Set<number>;
}

export const cardKey = (level: Level, index: number): string => `${level}:${index}`;
export const stubKey = (side: Side, id: number): string => `${side}:${id}`;

const bump = (found: Map<string, Sites>, key: string, partial: boolean, site: number): void => {
  const sites = found.get(key) ?? { proven: new Set<number>(), claim: new Set<number>() };
  sites[partial ? "claim" : "proven"].add(site);
  found.set(key, sites);
};
const tally = (sites: Sites): Tally => ({ proven: sites.proven.size, claim: sites.claim.size });

function center(box: LevelBox): readonly [number, number] {
  return [box.x + box.width / 2, box.y + box.height / 2];
}

/** A curve from one box to another, leaving and entering sideways. */
function curve(from: LevelBox, to: LevelBox): { path: string; middle: readonly [number, number] } {
  const [ax, ay] = center(from);
  const [bx, by] = center(to);
  const dx = (bx - ax) / 2;
  const bend = Math.abs(dx) < 40 ? 70 : dx;
  return {
    path: `M${ax} ${ay} C${ax + bend} ${ay} ${bx - bend} ${by} ${bx} ${by}`,
    middle: [(ax + bx) / 2, (ay + by) / 2],
  };
}

function arrange(
  level: Level,
  groups: readonly Group[],
  card: { readonly width: number; readonly height: number },
  stubsIn: readonly RawStub[],
  stubsOut: readonly RawStub[],
  raw: readonly RawLine[],
  hiddenCards: number,
): LevelLayout {
  const total = groups.reduce((sum, group) => sum + group.items.length, 0);
  const wide = total > WIDE && groups.length > 1;
  const perRow = wide ? 2 : total > 9 ? 3 : Math.max(1, Math.min(3, total));
  const plateColumns = wide ? 2 : 1;
  const plateWidth = perRow * (card.width + LEVEL_CARD.gap) + LEVEL_CARD.gap;
  const heights = new Array<number>(plateColumns).fill(0);
  const plates: LevelPlate[] = [];
  const cards: LevelCard[] = [];
  const left = LEVEL_STUB.width + SPREAD;
  for (const group of groups) {
    const column = heights.indexOf(Math.min(...heights));
    const rows = Math.ceil(group.items.length / perRow);
    const height = HEAD + rows * (card.height + LEVEL_CARD.gap) + LEVEL_CARD.gap;
    const x = left + column * (plateWidth + LEVEL_CARD.gap * 2);
    const y = heights[column];
    plates.push({ label: group.label, x, y, width: plateWidth, height });
    group.items.forEach((index, order) => {
      cards.push({
        index,
        x: x + LEVEL_CARD.gap + (order % perRow) * (card.width + LEVEL_CARD.gap),
        y: y + HEAD + LEVEL_CARD.gap + Math.floor(order / perRow) * (card.height + LEVEL_CARD.gap),
        width: card.width,
        height: card.height,
      });
    });
    heights[column] = y + height + LEVEL_CARD.gap * 2;
  }
  const centerWidth = plateColumns * plateWidth + (plateColumns - 1) * LEVEL_CARD.gap * 2;
  const shown = (stubs: readonly RawStub[]): RawStub[] =>
    [...stubs].sort((a, b) => b.proven + b.claim - (a.proven + a.claim)).slice(0, STUBS_SHOWN);
  const place = (side: Side, stubs: readonly RawStub[], height: number): LevelStub[] => {
    const rows = shown(stubs);
    const x = side === Side.In ? 0 : left + centerWidth + SPREAD;
    const top = Math.max(0, (height - rows.length * (LEVEL_STUB.height + LEVEL_STUB.gap)) / 2);
    return rows.map((stub, order) => ({
      ...stub,
      side,
      x,
      y: top + order * (LEVEL_STUB.height + LEVEL_STUB.gap),
      width: LEVEL_STUB.width,
      height: LEVEL_STUB.height,
    }));
  };
  const centerHeight = Math.max(0, ...heights);
  const stubHeight = (count: number): number => Math.min(count, STUBS_SHOWN) * (LEVEL_STUB.height + LEVEL_STUB.gap);
  const height = Math.max(centerHeight, stubHeight(stubsIn.length), stubHeight(stubsOut.length)) + 40;
  const stubs = [...place(Side.In, stubsIn, height), ...place(Side.Out, stubsOut, height)];
  const boxes = new Map<string, LevelBox>();
  cards.forEach((item) => boxes.set(cardKey(level, item.index), item));
  stubs.forEach((item) => boxes.set(stubKey(item.side, item.id), item));
  const drawn = raw.filter((line) => boxes.has(line.a) && boxes.has(line.b));
  const top = [...drawn].sort((a, b) => b.proven + b.claim - (a.proven + a.claim)).slice(0, LINES_SHOWN);
  const heaviest = Math.max(1, ...top.map((line) => line.proven + line.claim));
  const lines = top.map<LevelLine>((line) => {
    const calls = line.proven + line.claim;
    const { path, middle } = curve(boxes.get(line.a) as LevelBox, boxes.get(line.b) as LevelBox);
    return { ...line, path, middle, width: 1 + Math.min(3.5, Math.log2(1 + calls)), strong: calls / heaviest >= 0.1 };
  });
  return {
    width: left + centerWidth + SPREAD + LEVEL_STUB.width,
    height,
    plates,
    cards,
    stubs,
    lines,
    more: {
      stubs: Math.max(0, stubsIn.length - STUBS_SHOWN) + Math.max(0, stubsOut.length - STUBS_SHOWN),
      cards: hiddenCards,
    },
  };
}

const packageOf = (model: Model, module: number, fallback: string): string => model.folders[module].join(".") || fallback;

/** The modules of one component (or of one package of it), the lines between them and the other components as stubs. */
export function layoutComponent(model: Model, component: number, pkg: string | null): LevelLayout {
  const { graph } = model;
  const inside = (module: number): boolean => {
    if (graph.modules[module][2] !== component) return false;
    if (pkg === null) return true;
    const own = model.folders[module].join(".");
    return own === pkg || own.startsWith(`${pkg}.`);
  };
  const internal = new Map<string, Sites>();
  const callers = new Map<string, Sites>();
  const callees = new Map<string, Sites>();
  const lineIn = new Map<string, Sites>();
  const lineOut = new Map<string, Sites>();
  for (const [source, target, partial, , site] of graph.edges) {
    const from = graph.symbols[source][0];
    const to = graph.symbols[target][0];
    const fromComponent = graph.modules[from][2];
    const toComponent = graph.modules[to][2];
    if (inside(from) && inside(to) && from !== to) bump(internal, `${from}>${to}`, partial, site);
    else if (inside(from) && toComponent !== component) {
      bump(callees, `${toComponent}`, partial, site);
      bump(lineOut, `${from}>${toComponent}`, partial, site);
    } else if (inside(to) && fromComponent !== component) {
      bump(callers, `${fromComponent}`, partial, site);
      bump(lineIn, `${fromComponent}>${to}`, partial, site);
    }
  }
  const modules = graph.modules.map((_, module) => module).filter(inside);
  const name = (module: number): string => graph.modules[module][1].split("/").pop() ?? "";
  const packages = new Map<string, number[]>();
  for (const module of modules) {
    const key = packageOf(model, module, graph.components[component][0]);
    packages.set(key, [...(packages.get(key) ?? []), module]);
  }
  const groups = [...packages.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map<Group>(([label, items]) => ({ label, items: [...items].sort((a, b) => name(a).localeCompare(name(b))) }));
  const raw: RawLine[] = [];
  internal.forEach((sites, key) => {
    const [a, b] = key.split(">");
    raw.push({ ...tally(sites), a: cardKey(Level.Module, Number(a)), b: cardKey(Level.Module, Number(b)) });
  });
  lineIn.forEach((sites, key) => {
    const [id, to] = key.split(">");
    raw.push({ ...tally(sites), a: stubKey(Side.In, Number(id)), b: cardKey(Level.Module, Number(to)) });
  });
  lineOut.forEach((sites, key) => {
    const [from, id] = key.split(">");
    raw.push({ ...tally(sites), a: cardKey(Level.Module, Number(from)), b: stubKey(Side.Out, Number(id)) });
  });
  const stubs = (found: Map<string, Sites>): RawStub[] => [...found.entries()].map(([id, sites]) => ({ id: Number(id), ...tally(sites) }));
  return arrange(Level.Module, groups, LEVEL_CARD, stubs(callers), stubs(callees), raw, 0);
}

/** The functions of one module, their calls, and the modules that call in or are called as stubs. */
export function layoutModule(model: Model, module: number): LevelLayout {
  const { graph } = model;
  const all = [...model.members[module]].sort((a, b) => graph.symbols[a][2] - graph.symbols[b][2]);
  const shownFunctions = all.slice(0, FUNCTIONS_SHOWN);
  const shown = new Set(shownFunctions);
  const callers = new Map<number, { proven: number; claim: number }>();
  const callees = new Map<number, { proven: number; claim: number }>();
  const raw: RawLine[] = [];
  const count = (found: Map<number, { proven: number; claim: number }>, other: number, partial: boolean): void => {
    const now = found.get(other) ?? { proven: 0, claim: 0 };
    found.set(other, { proven: now.proven + (partial ? 0 : 1), claim: now.claim + (partial ? 1 : 0) });
  };
  const outside = new Set<string>();
  for (const symbol of all) {
    for (const link of model.outgoing[symbol]) {
      const other = graph.symbols[link.other][0];
      if (other === module) {
        if (shown.has(symbol) && shown.has(link.other)) {
          raw.push({
            proven: link.partial ? 0 : 1,
            claim: link.partial ? 1 : 0,
            a: cardKey(Level.Function, symbol),
            b: cardKey(Level.Function, link.other),
          });
        }
      } else {
        count(callees, other, link.partial);
        if (shown.has(symbol)) outside.add(`${Side.Out}:${other}>${symbol}`);
      }
    }
    for (const link of model.incoming[symbol]) {
      const other = graph.symbols[link.other][0];
      if (other !== module) {
        count(callers, other, link.partial);
        if (shown.has(symbol)) outside.add(`${Side.In}:${other}>${symbol}`);
      }
    }
  }
  // One thin line from a stub to each function it touches.
  for (const key of outside) {
    const [stub, symbol] = key.split(">");
    const [side, id] = stub.split(":");
    const sideKind = side === Side.In ? Side.In : Side.Out;
    const own = cardKey(Level.Function, Number(symbol));
    const other = stubKey(sideKind, Number(id));
    raw.push({ proven: 1, claim: 0, a: sideKind === Side.In ? other : own, b: sideKind === Side.In ? own : other });
  }
  const stubs = (found: Map<number, { proven: number; claim: number }>): RawStub[] =>
    [...found.entries()].map(([id, sites]) => ({ id, ...sites }));
  const label = graph.modules[module][1].split("/").pop() ?? graph.modules[module][0];
  return arrange(
    Level.Function,
    [{ label, items: shownFunctions }],
    { width: 210, height: 58 },
    stubs(callers),
    stubs(callees),
    raw,
    all.length - shownFunctions.length,
  );
}
