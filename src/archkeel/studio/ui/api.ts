/** AD-290: the client of schema/studio-api-1.0; it asks only its own server. */
export const ContractState = {
  NotConfigured: "not_configured",
  Invalid: "invalid",
  Configured: "configured",
} as const;
export type ContractState = (typeof ContractState)[keyof typeof ContractState];

export const ExploreState = {
  Idle: "idle",
  Running: "running",
  Done: "done",
  Failed: "failed",
} as const;
export type ExploreState = (typeof ExploreState)[keyof typeof ExploreState];

export type StudioState = {
  readonly api_version: "1.0.0";
  readonly root_name: string;
  readonly contract: ContractState;
  readonly explore: ExploreState;
  readonly seconds: number;
  readonly exit_code: number | null;
  readonly notes: readonly string[];
};

export const EXPLORER_PAGE = "/files/architecture.report.html";

export async function readState(): Promise<StudioState> {
  const response = await fetch("/api/v1/state", { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`GET /api/v1/state: ${response.status}`);
  }
  return await response.json();
}
