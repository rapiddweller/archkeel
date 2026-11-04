/** AD-290: the client of schema/studio-api-1.1; it asks only its own server. */
import {
  API_VERSION,
  AgentKind,
  ChatBlockKind,
  ChatError,
  ComponentSource,
  ContractState,
  ExploreState,
  SymbolKind,
} from "./vocabulary";

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
  unresolved: number,
  outside: number,
];
export type EdgeRow = readonly [source: number, target: number, partial: boolean, line: number, site: number];
export type UnknownRow = readonly [owner: number, expression: string, reason: string, line: number];

/** The call counts of the whole snapshot, as explore measured them. */
export type Totals = {
  readonly analyzed: number;
  readonly resolved: number;
  readonly partial: number;
  readonly unresolved: number;
};

export type Graph = {
  readonly components_from: ComponentSource;
  readonly totals: Totals;
  readonly snapshot: { readonly git_head: string; readonly source_digest: string; readonly dirty: boolean };
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

/** The call status of a step in `archkeel view check`; the client decides on these values. */
export const CheckStatus = {
  Proven: "proven",
  Declared: "declared",
  Claim: "claim",
  Unknown: "unknown",
  Missing: "missing",
} as const;
export type CheckStatus = (typeof CheckStatus)[keyof typeof CheckStatus];

/** Where a story spec lies: committed in the repository, or in the local cache folder. */
export const StorySource = { Repository: "repository", Local: "local" } as const;
export type StorySource = (typeof StorySource)[keyof typeof StorySource];

export type StoryRow = { readonly id: string; readonly title: string; readonly steps: number; readonly source: StorySource; readonly created: string | null };
export type Site = { readonly file: string | null; readonly line: number | null };
export type Seam = {
  readonly kind: "partial_call" | "unresolved_call";
  readonly node: string;
  readonly reason: string | null;
  readonly candidates?: number | null;
  readonly calls?: number | null;
};
export type Touch = { readonly system: string; readonly module: string; readonly library: string; readonly site: Site };
export type ExternalCheck = {
  readonly system: string;
  readonly touched: boolean;
  readonly evidence?: readonly Touch[];
  readonly direction?: string | null;
};
export type StoryStep = {
  readonly index: number;
  readonly node: string;
  readonly chapter: string | null;
  readonly title: string | null;
  readonly question: string | null;
  readonly lane: string | null;
  readonly defined_at: Site | null;
  readonly seam: Seam | null;
  readonly external: readonly ExternalCheck[];
};
/** A link of `steps`, by the index of the story step: the status of the call into that step. */
export type StepLink = {
  readonly source: string | null;
  readonly target: string;
  readonly status: CheckStatus;
  readonly reason: string;
  readonly note?: string | null;
  readonly evidence?: readonly { readonly file: string | null; readonly line: number | null; readonly candidates?: number }[];
};
export type StoryVerdict = Readonly<Record<CheckStatus, number>> & {
  readonly systems: readonly string[];
  readonly modules: number;
};
/** The part of the `archkeel view check` result (schema/view-check.schema.json) that the player draws. */
export type CheckedStory = {
  readonly title: string;
  readonly snapshot_current: boolean;
  readonly steps: readonly StepLink[];
  readonly author_notes: readonly string[];
  readonly story: {
    readonly id: string;
    readonly title: string;
    readonly chapters: readonly { readonly id: string; readonly title: string }[];
    readonly steps: readonly StoryStep[];
    readonly verdict: StoryVerdict;
    readonly limits?: readonly string[];
  } | null;
};
/** The text of a step is the `note` of the spec; the check result repeats it in `steps`. */

export type Fact = {
  readonly qualified_name: string;
  readonly file: string;
  readonly line: number;
  readonly resolved_callers: number;
  readonly resolved_callees: number;
  readonly unknown_calls: number;
};
export type ChatBlock = {
  readonly kind: ChatBlockKind;
  readonly text: string;
  readonly refs: readonly string[];
  readonly label: string | null;
};
export type ChatAnswer = {
  readonly agent: AgentKind;
  readonly blocks: readonly ChatBlock[];
  readonly facts: readonly Fact[];
  readonly dropped_refs: readonly string[];
  readonly applied: false;
};

/** A chat request that got no answer: the code of the JSON error body, else only the HTTP status. */
export class ChatFailed extends Error {
  readonly code: ChatError | null;
  readonly status: number;
  constructor(status: number, code: ChatError | null, detail: string) {
    super(detail);
    this.status = status;
    this.code = code;
  }
}

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

/** The header a page of another origin cannot send without a preflight (AD-292). */
const CHAT_HEADER = "X-Archkeel-Studio";

/** AD-292: ask the owner's agent; the answer is claims and proposals, and Studio's own facts. */
export async function askChat(question: string, context: string | null): Promise<ChatAnswer> {
  const response = await fetch("/api/v1/chat", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", [CHAT_HEADER]: "1" },
    body: JSON.stringify({ question, context }),
  });
  if (!response.ok) {
    // A 403 or 405 has a text body; the others have {error, detail}.
    const text = await response.text();
    let code: ChatError | null = null;
    let detail = text.trim() || `HTTP ${response.status}`;
    try {
      const body = JSON.parse(text);
      code = body.error ?? null;
      detail = body.detail ?? detail;
    } catch {
      // not JSON: keep the text
    }
    throw new ChatFailed(response.status, code, detail);
  }
  const answer: ChatAnswer & { readonly api_version: string } = await response.json();
  if (answer.api_version !== API_VERSION) {
    throw new Error(`The Studio API is ${answer.api_version}; this page needs ${API_VERSION}. Reload the page.`);
  }
  return answer;
}

export const readStories = async (): Promise<readonly StoryRow[]> =>
  (await get<{ api_version: string; stories: readonly StoryRow[] }>("/api/v1/stories")).stories;

/** One story: the check against the current snapshot, where the spec lies and where it comes from. */
export type StoryAnswer = {
  readonly checked: CheckedStory;
  readonly source: StorySource;
  /** The spec named another snapshot and was checked by node name against the current one. */
  readonly rebound: boolean;
  readonly created: {
    readonly created: string | null;
    readonly git_head: string | null;
    readonly author_kind: string | null;
    readonly agent: string | null;
  };
  /** The commit of the root now. */
  readonly head: string | null;
};

/** The checked story; a spec that does not check gives an error with the message. */
export async function readStory(id: string): Promise<StoryAnswer> {
  const path = `/api/v1/stories/${encodeURIComponent(id)}`;
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error((await response.text()).trim() || `GET ${path}: ${response.status}`);
  }
  return response.json();
}

/** A draft spec along the traced path from one function; the server writes nothing. */
export async function readDraft(from: string): Promise<unknown> {
  const path = `/api/v1/draft?from=${encodeURIComponent(from)}`;
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error((await response.text()).trim() || `GET ${path}: ${response.status}`);
  }
  return (await response.json()).spec;
}
