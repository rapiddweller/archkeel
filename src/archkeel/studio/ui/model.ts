/** AD-290: the indexed call graph of the snapshot. Pure functions; no DOM, no network. */
import type { Graph, UnknownRow } from "./api";

/** One distinct neighbor of a function. */
export interface Link {
  readonly other: number;
  readonly partial: boolean;
  readonly line: number;
}

/** Proven calls (resolved) and claims (partly resolved), counted as call sites, never as edges. */
export interface Tally {
  readonly proven: number;
  readonly claim: number;
}

/** The call sites from one component to another. */
export interface Flow extends Tally {
  readonly from: number;
  readonly to: number;
  /** The edges behind the line, as indexes into the edge list of the graph. */
  readonly edges: readonly number[];
}

export interface ComponentStats {
  readonly modules: number;
  readonly symbols: number;
  readonly callsIn: Tally;
  readonly callsOut: Tally;
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
  /** The call sites that cross a component border. */
  readonly crossing: Tally;
  readonly tree: readonly TreeNode[];
  /** The packages of each module inside its component; a package module sits in its own package. */
  readonly folders: readonly (readonly string[])[];
  /** The function that the lens shows when the user chose none. */
  readonly start: number | null;
}

/** The four levels of the drill-down: components, the modules of one, the functions of one, one function. */
export const Level = { Map: "map", Component: "component", Module: "module", Function: "function" } as const;
export type Level = (typeof Level)[keyof typeof Level];

/** A place on a level: the component, module or function index, and a package path inside a component. */
export interface Where {
  readonly level: Level;
  readonly id: number | null;
  readonly pkg: string | null;
}

export interface PlacePart {
  readonly label: string;
  /** The tree keys that open down to this part. */
  readonly keys: readonly string[];
  readonly where?: Where;
}

const SEARCH_MIN = 2;
const SEARCH_SCAN = 400;
const SEARCH_SHOWN = 12;

export const componentKey = (component: number): string => `c${component}`;
export const moduleKey = (module: number): string => `m${module}`;
export const symbolKey = (symbol: number): string => `f${symbol}`;

/** The one rule for two calls between the same functions: a resolved call wins over a partial one. */
const better = (known: { readonly partial: boolean } | undefined, call: { readonly partial: boolean }): boolean =>
  known === undefined || (known.partial && !call.partial);

function indexLinks(graph: Graph): { outgoing: Link[][]; incoming: Link[][] } {
  const out = graph.symbols.map(() => new Map<number, Link>());
  const inn = graph.symbols.map(() => new Map<number, Link>());
  for (const [source, target, partial, line] of graph.edges) {
    if (source === target) continue;
    if (better(out[source].get(target), { partial })) out[source].set(target, { other: target, partial, line });
    if (better(inn[target].get(source), { partial })) inn[target].set(source, { other: source, partial, line });
  }
  return {
    outgoing: out.map((links) => [...links.values()]),
    incoming: inn.map((links) => [...links.values()]),
  };
}

/** The distinct function pairs behind a line, a resolved call first. */
export function pairs(model: Model, flow: Flow): { source: number; target: number; partial: boolean; line: number }[] {
  const found = new Map<string, { source: number; target: number; partial: boolean; line: number }>();
  for (const index of flow.edges) {
    const [source, target, partial, line] = model.graph.edges[index];
    const key = `${source}:${target}`;
    if (better(found.get(key), { partial })) found.set(key, { source, target, partial, line });
  }
  return [...found.values()];
}

interface Counting {
  readonly flows: Flow[];
  readonly crossing: Tally;
  readonly out: readonly Tally[];
  readonly into: readonly Tally[];
}

/** Count call sites: a partly resolved call can give two edges but is one site. */
function countSites(graph: Graph): Counting {
  interface Draft {
    from: number;
    to: number;
    proven: Set<number>;
    claim: Set<number>;
    edges: number[];
  }
  const count = graph.components.length;
  const found = new Map<number, Draft>();
  const out = graph.components.map(() => ({ proven: new Set<number>(), claim: new Set<number>() }));
  const crossing = { proven: new Set<number>(), claim: new Set<number>() };
  graph.edges.forEach(([source, target, partial, , site], index) => {
    const from = graph.modules[graph.symbols[source][0]][2];
    const to = graph.modules[graph.symbols[target][0]][2];
    if (from === to) return;
    const key = from * count + to;
    const flow = found.get(key) ?? { from, to, proven: new Set<number>(), claim: new Set<number>(), edges: [] };
    const kind = partial ? "claim" : "proven";
    flow[kind].add(site);
    out[from][kind].add(site);
    crossing[kind].add(site);
    flow.edges.push(index);
    found.set(key, flow);
  });
  const flows = [...found.values()].map<Flow>((flow) => ({
    from: flow.from,
    to: flow.to,
    proven: flow.proven.size,
    claim: flow.claim.size,
    edges: flow.edges,
  }));
  // A claim with candidates in two components is one site for each of them.
  const into = graph.components.map<{ proven: number; claim: number }>(() => ({ proven: 0, claim: 0 }));
  for (const flow of flows) {
    into[flow.to].proven += flow.proven;
    into[flow.to].claim += flow.claim;
  }
  return {
    flows,
    crossing: { proven: crossing.proven.size, claim: crossing.claim.size },
    out: out.map((sites) => ({ proven: sites.proven.size, claim: sites.claim.size })),
    into,
  };
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
  const { flows, crossing, out, into } = countSites(graph);
  const links = (symbol: number): number => outgoing[symbol].length + incoming[symbol].length;
  const stats = graph.components.map<{ -readonly [K in keyof ComponentStats]: ComponentStats[K] }>(() => ({
    modules: 0,
    symbols: 0,
    callsIn: { proven: 0, claim: 0 },
    callsOut: { proven: 0, claim: 0 },
    withUnknown: 0,
    busiest: null,
  }));
  stats.forEach((stat, component) => {
    stat.callsIn = into[component];
    stat.callsOut = out[component];
  });
  graph.modules.forEach(([, , component]) => (stats[component].modules += 1));
  graph.symbols.forEach(([module], symbol) => {
    const own = stats[graph.modules[module][2]];
    own.symbols += 1;
    if (graph.symbols[symbol][5] > 0) own.withUnknown += 1;
    if (own.busiest === null || links(symbol) > links(own.busiest)) own.busiest = symbol;
  });
  // A function in the middle of a flow (called and calling) is a better first view than a hub.
  const middle = (symbol: number): number =>
    Math.min(incoming[symbol].length, outgoing[symbol].length) * 1e6 + links(symbol);
  let start: number | null = null;
  graph.symbols.forEach((_, symbol) => {
    if (start === null || middle(symbol) > middle(start)) start = symbol;
  });
  const folders = folderPaths(graph);
  const tree = buildTree(graph, folders);
  return { graph, outgoing, incoming, unknown, members, stats, flows, crossing, tree, folders, start };
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

const named = new WeakMap<Model, Map<string, number>>();

/** The symbol for a qualified name (module and symbol name), or null: a chat ref is a name. */
export function findSymbol(model: Model, name: string): number | null {
  let index = named.get(model);
  if (index === undefined) {
    index = new Map(model.graph.symbols.map((_, symbol) => [fullName(model, symbol), symbol]));
    named.set(model, index);
  }
  return index.get(name) ?? null;
}

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

/** The path of a place from the architecture down; the last part is the current one. */
export function trail(model: Model, where: Where): { parts: readonly PlacePart[]; current: string } {
  const root: PlacePart = { label: "Architecture", keys: [], where: { level: Level.Map, id: null, pkg: null } };
  if (where.level === Level.Map || where.id === null) return { parts: [], current: root.label };
  if (where.level === Level.Function) {
    const parts = locate(model, where.id);
    const withWhere = parts.map((part, index) => ({ ...part, where: whereOf(model, where.id as number, index) }));
    return { parts: [root, ...withWhere], current: model.graph.symbols[where.id][1] };
  }
  const module = where.level === Level.Module ? where.id : null;
  const component = module === null ? where.id : model.graph.modules[module][2];
  const packages = module === null ? (where.pkg?.split(".") ?? []) : model.folders[module];
  const parts: PlacePart[] = [root, { label: model.graph.components[component][0], keys: [componentKey(component)], where: { level: Level.Component, id: component, pkg: null } }];
  packages.forEach((name, index) => {
    const keys = [componentKey(component), ...packages.slice(0, index + 1).map((_, depth) => `${componentKey(component)}/${packages.slice(0, depth + 1).join("/")}`)];
    parts.push({ label: name, keys, where: { level: Level.Component, id: component, pkg: packages.slice(0, index + 1).join(".") } });
  });
  if (module === null) {
    const last = parts.pop();
    return { parts, current: last?.label ?? "" };
  }
  return { parts, current: model.graph.modules[module][1].split("/").pop() ?? "" };
}

/** The place of part `index` of `locate(symbol)`: component, packages, then the module. */
function whereOf(model: Model, symbol: number, index: number): Where {
  const module = moduleIndex(model, symbol);
  const component = model.graph.modules[module][2];
  const packages = model.folders[module];
  if (index === 0) return { level: Level.Component, id: component, pkg: null };
  if (index <= packages.length) return { level: Level.Component, id: component, pkg: packages.slice(0, index).join(".") };
  return { level: Level.Module, id: module, pkg: null };
}

/** The tree keys that open down to a place: only this branch is open. */
export function opened(model: Model, where: Where): ReadonlySet<string> {
  if (where.id === null || where.level === Level.Map) return new Set();
  if (where.level === Level.Function) return branch(model, where.id);
  if (where.level === Level.Module) return new Set(trailKeys(model, where.id));
  const keys = [componentKey(where.id)];
  where.pkg?.split(".").forEach((_, depth, all) => keys.push(`${componentKey(where.id as number)}/${all.slice(0, depth + 1).join("/")}`));
  return new Set(keys);
}

const trailKeys = (model: Model, module: number): readonly string[] => {
  const parts = locate(model, model.members[module][0] ?? 0);
  return model.members[module].length > 0 ? parts[parts.length - 1].keys : [componentKey(model.graph.modules[module][2])];
};

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
