/** AD-290: the indexed call graph of the snapshot. Pure functions; no DOM, no network. */
import type { Graph, UnknownRow } from "./api";

/** One distinct neighbor of a function; a resolved call wins over a partial one. */
export interface Link {
  readonly other: number;
  readonly partial: boolean;
  readonly line: number;
}

/** The calls between two components, counted for every call site. */
export interface Flow {
  readonly from: number;
  readonly to: number;
  readonly calls: number;
  readonly partial: number;
  readonly edges: readonly number[];
}

export interface ComponentStats {
  readonly modules: number;
  readonly symbols: number;
  readonly callsIn: number;
  readonly callsOut: number;
  readonly withUnknown: number;
  /** The function with most links, or null for a component without functions. */
  readonly busiest: number | null;
}

export interface TreeNode {
  readonly key: string;
  readonly label: string;
  readonly count: number;
  readonly kids: readonly TreeNode[];
  /** The modules directly below this node. */
  readonly modules: readonly number[];
}

export interface Model {
  readonly graph: Graph;
  readonly outgoing: readonly (readonly Link[])[];
  readonly incoming: readonly (readonly Link[])[];
  readonly unknown: readonly (readonly UnknownRow[])[];
  readonly members: readonly (readonly number[])[];
  readonly stats: readonly ComponentStats[];
  readonly flows: readonly Flow[];
  readonly tree: readonly TreeNode[];
  /** The packages of each module inside its component; a package module sits in its own package. */
  readonly folders: readonly (readonly string[])[];
  /** The function that the lens shows when the user chose none. */
  readonly start: number | null;
}

export interface PlacePart {
  readonly label: string;
  /** The tree keys that open down to this part. */
  readonly keys: readonly string[];
}

const SEARCH_MIN = 2;
const SEARCH_SCAN = 400;
const SEARCH_SHOWN = 12;

export const componentKey = (component: number): string => `c${component}`;
export const moduleKey = (module: number): string => `m${module}`;
export const symbolKey = (symbol: number): string => `f${symbol}`;

function distinct(links: Map<number, Link>[], owner: number, link: Link): void {
  const known = links[owner].get(link.other);
  if (known === undefined || (known.partial && !link.partial)) links[owner].set(link.other, link);
}

function indexLinks(graph: Graph): { outgoing: Link[][]; incoming: Link[][] } {
  const out = graph.symbols.map(() => new Map<number, Link>());
  const inn = graph.symbols.map(() => new Map<number, Link>());
  for (const [source, target, partial, line] of graph.edges) {
    if (source === target) continue;
    distinct(out, source, { other: target, partial, line });
    distinct(inn, target, { other: source, partial, line });
  }
  return {
    outgoing: out.map((links) => [...links.values()]),
    incoming: inn.map((links) => [...links.values()]),
  };
}

function groupFlows(graph: Graph): Flow[] {
  const found = new Map<number, { from: number; to: number; calls: number; partial: number; edges: number[] }>();
  const count = graph.components.length;
  graph.edges.forEach(([source, target, partial], index) => {
    const from = graph.modules[graph.symbols[source][0]][2];
    const to = graph.modules[graph.symbols[target][0]][2];
    if (from === to) return;
    const key = from * count + to;
    const flow = found.get(key) ?? { from, to, calls: 0, partial: 0, edges: [] };
    flow.calls += 1;
    flow.partial += partial ? 1 : 0;
    flow.edges.push(index);
    found.set(key, flow);
  });
  return [...found.values()];
}

function folderPaths(graph: Graph): string[][] {
  const parents = new Set<string>();
  for (const [, , component, relative] of graph.modules) {
    const parts = relative.split(".");
    for (let length = 1; length < parts.length; length += 1) {
      parents.add(`${component}:${parts.slice(0, length).join(".")}`);
    }
  }
  return graph.modules.map(([, , component, relative]) => {
    const parts = relative.split(".");
    return parents.has(`${component}:${relative}`) ? parts : parts.slice(0, -1);
  });
}

function buildTree(graph: Graph, folders: readonly (readonly string[])[]): TreeNode[] {
  interface Draft {
    key: string;
    label: string;
    kids: Map<string, Draft>;
    modules: number[];
  }
  const roots = graph.components.map<Draft>(([id], index) => ({
    key: componentKey(index),
    label: id,
    kids: new Map(),
    modules: [],
  }));
  graph.modules.forEach(([, , component], index) => {
    let node = roots[component];
    for (const part of folders[index]) {
      const key = `${node.key}/${part}`;
      const kid = node.kids.get(part) ?? { key, label: part, kids: new Map(), modules: [] };
      node.kids.set(part, kid);
      node = kid;
    }
    node.modules.push(index);
  });
  const freeze = (draft: Draft): TreeNode => {
    const kids = [...draft.kids.values()].sort((a, b) => a.label.localeCompare(b.label)).map(freeze);
    const count = draft.modules.length + kids.reduce((sum, kid) => sum + kid.count, 0);
    return { key: draft.key, label: draft.label, count, kids, modules: draft.modules };
  };
  return roots.map(freeze);
}

export function buildModel(graph: Graph): Model {
  const { outgoing, incoming } = indexLinks(graph);
  const unknown = graph.symbols.map<UnknownRow[]>(() => []);
  for (const row of graph.unknown) unknown[row[0]].push(row);
  const members = graph.modules.map<number[]>(() => []);
  graph.symbols.forEach(([module], symbol) => members[module].push(symbol));
  const flows = groupFlows(graph);
  const links = (symbol: number): number => outgoing[symbol].length + incoming[symbol].length;
  const stats = graph.components.map<{ -readonly [K in keyof ComponentStats]: ComponentStats[K] }>(() => ({
    modules: 0,
    symbols: 0,
    callsIn: 0,
    callsOut: 0,
    withUnknown: 0,
    busiest: null,
  }));
  graph.modules.forEach(([, , component]) => (stats[component].modules += 1));
  graph.symbols.forEach(([module], symbol) => {
    const own = stats[graph.modules[module][2]];
    own.symbols += 1;
    if (unknown[symbol].length > 0) own.withUnknown += 1;
    if (own.busiest === null || links(symbol) > links(own.busiest)) own.busiest = symbol;
  });
  for (const flow of flows) {
    stats[flow.from].callsOut += flow.calls;
    stats[flow.to].callsIn += flow.calls;
  }
  // A function in the middle of a flow (called and calling) is a better first view than a hub.
  const middle = (symbol: number): number =>
    Math.min(incoming[symbol].length, outgoing[symbol].length) * 1e6 + links(symbol);
  let start: number | null = null;
  graph.symbols.forEach((_, symbol) => {
    if (start === null || middle(symbol) > middle(start)) start = symbol;
  });
  const folders = folderPaths(graph);
  const tree = buildTree(graph, folders);
  return { graph, outgoing, incoming, unknown, members, stats, flows, tree, folders, start };
}

/** 1,234 reads 1.2k; counts of a large repository stay short on a card. */
export const compact = (count: number): string =>
  count >= 1000 ? `${(count / 1000).toFixed(count >= 10000 ? 0 : 1)}k` : `${count}`;

/** "1 caller", "2 callers". */
export const counted = (count: number, noun: string): string => `${count} ${noun}${count === 1 ? "" : "s"}`;

export const links = (model: Model, symbol: number): number =>
  model.outgoing[symbol].length + model.incoming[symbol].length;

export const moduleIndex = (model: Model, symbol: number): number => model.graph.symbols[symbol][0];

export const componentOf = (model: Model, symbol: number): number =>
  model.graph.modules[moduleIndex(model, symbol)][2];

/** The name of the function without its class and module. */
export const shortName = (model: Model, symbol: number): string => {
  const parts = model.graph.symbols[symbol][1].split(".");
  return parts[parts.length - 1];
};

export const fullName = (model: Model, symbol: number): string =>
  `${model.graph.modules[moduleIndex(model, symbol)][0]}.${model.graph.symbols[symbol][1]}`;

export const fileName = (model: Model, symbol: number): string =>
  model.graph.modules[moduleIndex(model, symbol)][1];

/** The last two parts of a path: the folder and the file. */
export const tailPath = (path: string): string => path.split("/").slice(-2).join("/");

/** The end of a dotted name; the end tells modules apart. */
export function tailName(name: string, limit: number): string {
  return name.length <= limit ? name : `…${name.slice(name.length - limit + 1)}`;
}

/** The group that a large neighborhood folds into: the component and its first package. */
export function groupOf(model: Model, symbol: number): string {
  const row = model.graph.modules[moduleIndex(model, symbol)];
  const parts = row[3].split(".");
  const id = model.graph.components[row[2]][0];
  return parts.length > 1 ? `${id}.${parts[0]}` : id;
}

/** Where a function sits: the component, its packages and its module file. */
export function locate(model: Model, symbol: number): readonly PlacePart[] {
  const module = moduleIndex(model, symbol);
  const [, file, component] = model.graph.modules[module];
  const parts: PlacePart[] = [];
  let keys: string[] = [componentKey(component)];
  parts.push({ label: model.graph.components[component][0], keys });
  for (const name of model.folders[module]) {
    keys = [...keys, `${keys[keys.length - 1]}/${name}`];
    parts.push({ label: name, keys });
  }
  parts.push({ label: file.split("/").pop() ?? file, keys: [...keys, moduleKey(module)] });
  return parts;
}

/** The tree keys that show a function: all its ancestors, so only this branch is open. */
export function branch(model: Model, symbol: number): ReadonlySet<string> {
  const parts = locate(model, symbol);
  return new Set(parts[parts.length - 1].keys);
}

/** Functions by name or module; names that start with the text come first, then busy ones. */
export function search(model: Model, text: string): number[] {
  const needle = text.trim().toLowerCase();
  if (needle.length < SEARCH_MIN) return [];
  const found: number[] = [];
  for (let symbol = 0; symbol < model.graph.symbols.length && found.length < SEARCH_SCAN; symbol += 1) {
    if (fullName(model, symbol).toLowerCase().includes(needle)) found.push(symbol);
  }
  const rank = (symbol: number): number => (shortName(model, symbol).toLowerCase().startsWith(needle) ? 0 : 1);
  found.sort((a, b) => rank(a) - rank(b) || links(model, b) - links(model, a));
  return found.slice(0, SEARCH_SHOWN);
}
