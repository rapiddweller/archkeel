/** AD-290: the client of schema/studio-api-1.1; it asks only its own server. */
import { API_VERSION, ContractState, ExploreState, SymbolKind } from "./vocabulary";

export type StudioState = {
  readonly api_version: typeof API_VERSION;
  readonly root_name: string;
  readonly contract: ContractState;
  readonly explore: ExploreState;
  readonly seconds: number;
  readonly exit_code: number | null;
  readonly notes: readonly string[];
};

/** A row is an array; a number that names a row of another list is its index. */
export type ComponentRow = readonly [id: string, responsibility: string];
export type ModuleRow = readonly [name: string, file: string, component: number, relative: string];
export type SymbolRow = readonly [
  module: number,
  name: string,
  line: number,
  kind: SymbolKind,
  text: string,
];
export type EdgeRow = readonly [source: number, target: number, partial: boolean, line: number];
export type UnknownRow = readonly [owner: number, expression: string, reason: string, line: number];

export type Graph = {
  readonly components: readonly ComponentRow[];
  readonly modules: readonly ModuleRow[];
  readonly symbols: readonly SymbolRow[];
  readonly edges: readonly EdgeRow[];
  readonly unknown: readonly UnknownRow[];
};

type GraphAnswer = {
  readonly api_version: typeof API_VERSION;
  readonly explore: ExploreState;
  readonly graph: Graph | null;
};

export const EXPLORER_PAGE = "/files/architecture.report.html";

async function get<Answer extends { readonly api_version: string }>(path: string): Promise<Answer> {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`GET ${path}: ${response.status}`);
  }
  const answer: Answer = await response.json();
  // One wheel ships both sides; a mismatch means a page of another Studio run.
  if (answer.api_version !== API_VERSION) {
    throw new Error(
      `The Studio API is ${answer.api_version}; this page needs ${API_VERSION}. Reload the page.`,
    );
  }
  return answer;
}

export const readState = (): Promise<StudioState> => get<StudioState>("/api/v1/state");

/** The call graph of the finished snapshot; null while the explore run is not done. */
export async function readGraph(): Promise<Graph | null> {
  return (await get<GraphAnswer>("/api/v1/graph")).graph;
}
