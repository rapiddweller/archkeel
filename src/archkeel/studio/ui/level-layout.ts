/** AD-290: the layouts of the levels below the Map: the modules of a component, the functions of a module. Pure. */
import { better, proofOf } from "./evidence";
import { Side } from "./lens-layout";
import { cardHeight } from "./measure";
import { Level, Model, Tally, fileOf } from "./model";

/** Sizes at scale 1. The default fit shows them at about 0.9, so no text is below 10 px. */
const LEVEL_CARD = { width: 200, height: 56, gap: 24 } as const;
const LEVEL_STUB = { width: 170, height: 92, gap: 14 } as const;

/** What a card says, so that the layout can size it to the text. */
export interface LevelText {
  readonly card: (index: number) => { readonly name: string; readonly facts: readonly string[] };
  readonly stub: (ref: string) => { readonly name: string; readonly facts: readonly string[] };
}
const HEAD = 30;
const SPREAD = 56;
const COLUMNS = 2;
const STUBS_SHOWN = 8;
/** Room above the first plate and stub: the column labels have a row of their own. */
const TOP = 40;
/** At most this many cards show at first; the rest of a package folds into one tile. */
const MODULES_SHOWN = 8;
export const FUNCTIONS_SHOWN = 16;
const PAIRS_KEPT = 60;

export interface LevelBox {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}
interface LevelCard extends LevelBox {
  /** The module or the function. */
  readonly index: number;
}
interface LevelPlate extends LevelBox {
  /** The package, or the module file on the level of the functions. */
  readonly label: string;
}
/** A folded package or the rest of a plate: one card that opens it. */
interface LevelTile extends LevelBox {
  readonly label: string;
  readonly hidden: number;
}
/**
 * Another component, another package of the component, or another module that calls in or is called.
 * `ref` is the component, `component/package` or the module.
 */
export interface LevelStub extends LevelBox, Tally {
  readonly side: Side;
  readonly ref: string;
}
/** One function pair behind a link; the line is the call site in the file of the source. */
interface LevelPair {
  readonly source: number;
  readonly target: number;
  readonly partial: boolean;
  readonly line: number;
}
export interface LevelLink extends Tally {
  readonly a: string;
  readonly b: string;
  readonly pairs: readonly LevelPair[];
}
/** The faint line of a stub at rest: from the stub to a port on the edge of the nearest plate or tile. */
interface LevelAggregate {
  readonly key: string;
  readonly points: readonly (readonly [number, number])[];
}
export interface LevelLayout {
  readonly width: number;
  readonly height: number;
  readonly plates: readonly LevelPlate[];
  readonly cards: readonly LevelCard[];
  readonly tiles: readonly LevelTile[];
  readonly stubs: readonly LevelStub[];
  readonly links: readonly LevelLink[];
  readonly aggregates: readonly LevelAggregate[];
  /** Stubs that did not fit the drawing, counted. */
  readonly moreStubs: number;
  /** Where the columns of the stubs start. */
  readonly columns: { readonly in: number; readonly out: number };
}

interface Group {
  readonly label: string;
  /** Drawn as cards. */
  readonly items: readonly number[];
  /** Held by the tile of the group; with no `items` the group has no plate, only the tile. */
  readonly rest: readonly number[];
}
interface RawStub extends Tally {
  readonly ref: string;
}
/** The call sites stay sets until the end: two links that merge must not count one site twice. */
interface RawLink {
  readonly a: string;
  readonly b: string;
  readonly proven: ReadonlySet<number>;
  readonly claim: ReadonlySet<number>;
  readonly pairs: readonly LevelPair[];
}
interface Sites {
  readonly proven: Set<number>;
  readonly claim: Set<number>;
  readonly pairs: Map<string, LevelPair>;
}

export const cardKey = (level: Level, index: number): string => `${level}:${index}`;
export const stubKey = (side: Side, ref: string): string => `${side}:${ref}`;
export const tileKey = (label: string): string => `tile:${label}`;

/** What a key names. */
export const KeyKind = { Stub: "stub", Tile: "tile", Card: "card" } as const;
export type KeyKind = (typeof KeyKind)[keyof typeof KeyKind];
type KeyPart = { readonly kind: KeyKind; readonly stub: Side | null; readonly ref: string };
export function parseKey(key: string): KeyPart {
  const at = key.indexOf(":");
  const head = key.slice(0, at);
  const ref = key.slice(at + 1);
  if (head === Side.In || head === Side.Out) return { kind: KeyKind.Stub, stub: head, ref };
  return { kind: key.startsWith(tileKey("")) ? KeyKind.Tile : KeyKind.Card, stub: null, ref };
}

/** The component and the package of a stub of the component level. */
export function splitRef(ref: string): { readonly id: number; readonly pkg: string | null } {
  const [id, ...pkg] = ref.split("/");
  return { id: Number(id), pkg: pkg.length > 0 ? pkg.join("/") : null };
}

const bump = (found: Map<string, Sites>, key: string, pair: LevelPair, site: number): void => {
  const sites = found.get(key) ?? { proven: new Set<number>(), claim: new Set<number>(), pairs: new Map<string, LevelPair>() };
  sites[proofOf(pair.partial)].add(site);
  const id = `${pair.source}:${pair.target}`;
  if (better(sites.pairs.get(id), pair)) sites.pairs.set(id, pair);
  found.set(key, sites);
};
const raw = (key: [string, string], sites: Sites): RawLink => ({
  a: key[0],
  b: key[1],
  proven: sites.proven,
  claim: sites.claim,
  pairs: [...sites.pairs.values()].slice(0, PAIRS_KEPT),
});
const toLink = (link: RawLink): LevelLink => ({ a: link.a, b: link.b, proven: link.proven.size, claim: link.claim.size, pairs: link.pairs });
const stubsOf = (found: ReadonlyMap<string, Sites>): RawStub[] =>
  [...found.entries()].map(([ref, sites]) => ({ ref, proven: sites.proven.size, claim: sites.claim.size }));

/** A link to a card that a tile holds ends on the tile; two links with the same ends become one and share their sites. */
function remap(links: readonly RawLink[], tileOf: ReadonlyMap<string, string>): RawLink[] {
  const merged = new Map<string, RawLink>();
  for (const link of links) {
    const a = tileOf.get(link.a) ?? link.a;
    const b = tileOf.get(link.b) ?? link.b;
    if (a === b) continue;
    const key = `${a}|${b}`;
    const known = merged.get(key);
    merged.set(key, {
      a,
      b,
      proven: new Set([...(known?.proven ?? []), ...link.proven]),
      claim: new Set([...(known?.claim ?? []), ...link.claim]),
      pairs: [...(known?.pairs ?? []), ...link.pairs].slice(0, PAIRS_KEPT),
    });
  }
  return [...merged.values()];
}

function arrange(
  level: Level,
  groups: readonly Group[],
  stubsIn: readonly RawStub[],
  stubsOut: readonly RawStub[],
  links: readonly RawLink[],
  text: LevelText,
): LevelLayout {
  const { width: cardWidth, height: minimum, gap } = LEVEL_CARD;
  const heightOf = (index: number): number => {
    const { name, facts } = text.card(index);
    return Math.max(minimum, cardHeight(cardWidth, name, facts));
  };
  const total = groups.reduce((sum, group) => sum + group.items.length + group.rest.length, 0);
  const columns = total <= 1 ? 1 : COLUMNS;
  const plateWidth = columns * cardWidth + (columns + 1) * gap;
  const left = LEVEL_STUB.width + SPREAD;
  const plates: LevelPlate[] = [];
  const cards: LevelCard[] = [];
  const tiles: LevelTile[] = [];
  const tileOf = new Map<string, string>();
  let y = TOP;
  for (const group of groups) {
    group.rest.forEach((index) => tileOf.set(cardKey(level, index), tileKey(group.label)));
    if (group.items.length === 0) {
      // A folded package has no plate: one tile in its place.
      tiles.push({ label: group.label, hidden: group.rest.length, x: left, y, width: plateWidth, height: minimum });
      y += minimum + gap;
      continue;
    }
    // A row of cards is as tall as its tallest card; every card of the row has that height.
    const rows: number[][] = [];
    group.items.forEach((index, order) => {
      if (order % columns === 0) rows.push([]);
      rows[rows.length - 1].push(index);
    });
    const rowHeights = rows.map((row) => Math.max(...row.map(heightOf)));
    const body = rowHeights.reduce((sum, height) => sum + height + gap, gap);
    // The tile of the rest sits in a row of its own at the bottom of the plate.
    const height = HEAD + body + (group.rest.length > 0 ? minimum + gap : 0);
    plates.push({ label: group.label, x: left, y, width: plateWidth, height });
    if (group.rest.length > 0) {
      tiles.push({ label: group.label, hidden: group.rest.length, x: left + gap, y: y + height - gap - minimum, width: plateWidth - 2 * gap, height: minimum });
    }
    let top = y + HEAD + gap;
    rows.forEach((row, at) => {
      row.forEach((index, order) => {
        cards.push({ index, x: left + gap + order * (cardWidth + gap), y: top, width: cardWidth, height: rowHeights[at] });
      });
      top += rowHeights[at] + gap;
    });
    y += height + gap;
  }
  const centerHeight = Math.max(0, y - gap);
  const stubSize = (stub: RawStub): number => {
    const { name, facts } = text.stub(stub.ref);
    // One more line holds the functions on the other side while a card has the focus.
    return Math.max(minimum, cardHeight(LEVEL_STUB.width, name, [...facts, ""]));
  };
  const shownStubs = (stubs: readonly RawStub[]): RawStub[] =>
    [...stubs].sort((a, b) => b.proven + b.claim - (a.proven + a.claim)).slice(0, STUBS_SHOWN);
  const stackHeight = (stubs: readonly RawStub[]): number =>
    shownStubs(stubs).reduce((sum, stub) => sum + stubSize(stub) + LEVEL_STUB.gap, 0);
  const height = Math.max(centerHeight, TOP + stackHeight(stubsIn), TOP + stackHeight(stubsOut)) + 24;
  const place = (side: Side, stubs: readonly RawStub[]): LevelStub[] => {
    const rows = shownStubs(stubs);
    const x = side === Side.In ? 0 : left + plateWidth + SPREAD;
    let top = Math.max(TOP, (height - stackHeight(stubs)) / 2);
    return rows.map((stub) => {
      const size = stubSize(stub);
      const placed = { ...stub, side, x, y: top, width: LEVEL_STUB.width, height: size };
      top += size + LEVEL_STUB.gap;
      return placed;
    });
  };
  const stubs = [...place(Side.In, stubsIn), ...place(Side.Out, stubsOut)];
  const merged = remap(links, tileOf);
  const drawn = new Set<string>([
    ...cards.map((card) => cardKey(level, card.index)),
    ...tiles.map((tile) => tileKey(tile.label)),
    ...stubs.map((stub) => stubKey(stub.side, stub.ref)),
  ]);
  // At rest a stub has a faint line to a port on the edge of the plate or tile that is nearest to it.
  const targets: LevelBox[] = [...plates, ...tiles];
  const aggregates = stubs.flatMap<LevelAggregate>((stub) => {
    const centre = stub.y + stub.height / 2;
    const nearest = [...targets].sort((p, q) => Math.abs(centre - (p.y + p.height / 2)) - Math.abs(centre - (q.y + q.height / 2)))[0];
    if (nearest === undefined) return [];
    const inbound = stub.side === Side.In;
    const from: readonly [number, number] = [inbound ? stub.x + stub.width : stub.x, centre];
    const port: readonly [number, number] = [inbound ? nearest.x : nearest.x + nearest.width, Math.min(Math.max(centre, nearest.y + 12), nearest.y + nearest.height - 12)];
    const middle = (from[0] + port[0]) / 2;
    return [{ key: stubKey(stub.side, stub.ref), points: [from, [middle, from[1]], [middle, port[1]], port] }];
  });
  return {
    width: left + plateWidth + SPREAD + LEVEL_STUB.width,
    height,
    plates,
    cards,
    tiles,
    stubs,
    links: merged.filter((link) => drawn.has(link.a) && drawn.has(link.b)).map(toLink),
    aggregates,
    moreStubs: Math.max(0, stubsIn.length - STUBS_SHOWN) + Math.max(0, stubsOut.length - STUBS_SHOWN),
    columns: { in: 0, out: left + plateWidth + SPREAD },
  };
}

/** Packages in order. One that does not fit the budget folds, unless the user opened it; the first one shows its first modules. */
function fold(groups: readonly { label: string; items: readonly number[] }[], opened: ReadonlySet<string>, budget: number): Group[] {
  let used = 0;
  return groups.map((group) => {
    if (opened.has(group.label) || used + group.items.length <= budget) {
      used += group.items.length;
      return { ...group, rest: [] };
    }
    if (used === 0) {
      used = budget;
      return { label: group.label, items: group.items.slice(0, budget), rest: group.items.slice(budget) };
    }
    return { label: group.label, items: [], rest: group.items };
  });
}

const packageOf = (model: Model, module: number): string => model.folders[module].join(".");

/** The modules of one component (or of one package of it), the links between them and the other components and packages as stubs. */
export function layoutComponent(model: Model, component: number, pkg: string | null, opened: ReadonlySet<string>, text: LevelText): LevelLayout {
  const { graph } = model;
  const inside = (module: number): boolean => {
    if (graph.modules[module][2] !== component) return false;
    if (pkg === null) return true;
    const own = packageOf(model, module);
    return own === pkg || own.startsWith(`${pkg}.`);
  };
  /** The stub of a module outside the page: its component, or its package when it is in this component. */
  const outside = (module: number): string => {
    const other = graph.modules[module][2];
    const own = packageOf(model, module);
    return other === component && own !== "" ? `${other}/${own}` : `${other}`;
  };
  const internal = new Map<string, Sites>();
  const callers = new Map<string, Sites>();
  const callees = new Map<string, Sites>();
  const linkIn = new Map<string, Sites>();
  const linkOut = new Map<string, Sites>();
  for (const [source, target, partial, line, site] of graph.edges) {
    const from = graph.symbols[source][0];
    const to = graph.symbols[target][0];
    const pair: LevelPair = { source, target, partial, line };
    if (inside(from) && inside(to)) {
      if (from !== to) bump(internal, `${from}>${to}`, pair, site);
    } else if (inside(from)) {
      bump(callees, outside(to), pair, site);
      bump(linkOut, `${from}>${outside(to)}`, pair, site);
    } else if (inside(to)) {
      bump(callers, outside(from), pair, site);
      bump(linkIn, `${outside(from)}>${to}`, pair, site);
    }
  }
  const modules = graph.modules.map((_, module) => module).filter(inside);
  const name = (module: number): string => fileOf(model, module);
  const packages = new Map<string, number[]>();
  for (const module of modules) {
    const key = packageOf(model, module) || graph.components[component][0];
    packages.set(key, [...(packages.get(key) ?? []), module]);
  }
  const groups = [...packages.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, items]) => ({ label, items: [...items].sort((a, b) => name(a).localeCompare(name(b))) }));
  const links: RawLink[] = [];
  internal.forEach((sites, key) => {
    const [a, b] = key.split(">");
    links.push(raw([cardKey(Level.Module, Number(a)), cardKey(Level.Module, Number(b))], sites));
  });
  linkIn.forEach((sites, key) => {
    const [ref, to] = key.split(">");
    links.push(raw([stubKey(Side.In, ref), cardKey(Level.Module, Number(to))], sites));
  });
  linkOut.forEach((sites, key) => {
    const [from, ref] = key.split(">");
    links.push(raw([cardKey(Level.Module, Number(from)), stubKey(Side.Out, ref)], sites));
  });
  return arrange(Level.Module, fold(groups, opened, MODULES_SHOWN), stubsOf(callers), stubsOf(callees), links, text);
}

/** The functions of one module, their calls, and the modules that call in or are called as stubs. Counts call sites, not function pairs. */
export function layoutModule(model: Model, module: number, showAll: boolean, text: LevelText): LevelLayout {
  const { graph } = model;
  const all = [...model.members[module]].sort((a, b) => graph.symbols[a][2] - graph.symbols[b][2]);
  const shownFunctions = showAll ? all : all.slice(0, FUNCTIONS_SHOWN);
  const callers = new Map<string, Sites>();
  const callees = new Map<string, Sites>();
  /** Keyed `a|b` by the two ends of the link. */
  const joined = new Map<string, Sites>();
  for (const [source, target, partial, line, site] of graph.edges) {
    if (source === target) continue;
    const from = graph.symbols[source][0];
    const to = graph.symbols[target][0];
    const pair: LevelPair = { source, target, partial, line };
    if (from === module && to === module) {
      bump(joined, `${cardKey(Level.Function, source)}|${cardKey(Level.Function, target)}`, pair, site);
    } else if (from === module) {
      bump(callees, `${to}`, pair, site);
      bump(joined, `${cardKey(Level.Function, source)}|${stubKey(Side.Out, `${to}`)}`, pair, site);
    } else if (to === module) {
      bump(callers, `${from}`, pair, site);
      bump(joined, `${stubKey(Side.In, `${from}`)}|${cardKey(Level.Function, target)}`, pair, site);
    }
  }
  const links: RawLink[] = [];
  joined.forEach((sites, key) => {
    const [a, b] = key.split("|");
    links.push(raw([a, b], sites));
  });
  const label = fileOf(model, module);
  const groups: Group[] = [{ label, items: shownFunctions, rest: all.slice(shownFunctions.length) }];
  return arrange(Level.Function, groups, stubsOf(callers), stubsOf(callees), links, text);
}
