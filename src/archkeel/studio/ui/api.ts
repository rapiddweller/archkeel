/** AD-290: the client of schema/studio-api-1.0; it asks only its own server. */
import { API_VERSION, ContractState, ExploreState } from "./vocabulary";

export type StudioState = {
  readonly api_version: typeof API_VERSION;
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
