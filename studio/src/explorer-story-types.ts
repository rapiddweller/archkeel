import type { StudioEdge } from "./studio-model.js";

export interface StorySite {
  path?: string | null;
  file?: string | null;
  line?: number | null;
  reference?: string | null;
}

export interface StoryExternal {
  system: string;
  label?: string;
  status: "observed_call" | "claim";
  binding?: "external" | "unknown";
  reason?: string;
  evidence: StorySite[];
  direction?: "reads" | "writes" | "reads_writes" | "touches" | "unknown";
  direction_evidence?: StorySite[];
  direction_reason?: string;
}

interface StoryDetails {
  chapter?: string | null;
  title?: string | null;
  lane?: string | null;
  function?: string;
  expression?: string | null;
  note?: string | null;
  question?: string | null;
  reason?: string | null;
  transition?: string;
  defined_at?: StorySite | null;
  evidence?: StorySite[];
  external?: StoryExternal[];
}

interface CheckedStep extends StoryDetails {
  node: string;
  status: string;
}

export interface CallStoryHop extends StudioEdge {
  source_owner?: string | null;
  target_owner?: string | null;
}

export type StoryHop = CallStoryHop | CheckedStep;
export type StoryDisplayStep = StoryDetails & { name?: string; status: string };

export interface StorySummary {
  id: string;
  title?: string;
}

export interface CheckedStory extends StorySummary {
  title: string;
  chapters: { id: string; title: string }[];
  coverage: { observed_only?: boolean };
  steps: CheckedStep[];
}
