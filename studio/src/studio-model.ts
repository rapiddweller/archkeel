export interface StudioItem {
  system_part?: boolean;
  id: string;
  name: string;
  kind: string;
  parent?: string | null;
  path?: string;
  source?: string;
  display_name?: string;
  language?: string;
  responsibilities?: string[];
  public?: string[];
  collapsed?: boolean;
  module_count?: number;
  recorded_calls?: number;
  unresolved_calls?: number;
  property_names?: string[];
  member_coverage?: Record<string, string>;
  members_complete?: boolean;
  annotation?: string;
  open_target?: "map" | "source";
}

export interface StudioEdge {
  id: string;
  source: string;
  target: string | null;
  source_name?: string | null;
  target_name?: string | null;
  kind: string;
  resolution: string;
  title?: string;
  expression?: string;
  declaration?: string;
  reason?: string;
  rationale?: string;
  schema?: string;
  aggregate?: boolean;
  aggregate_id?: string;
  count?: number;
  evidence?: { path: string; line: number; role?: string }[];
  evidence_total?: number;
}

export interface StudioCoverage {
  parts?: { part?: string; language?: string; files_indexed?: number | null; files_with_symbols?: number | null; facts?: { calls?: number | null }; files_with_calls?: number | null }[];
  total?: Record<string, number>;
  observed_only?: boolean;
  truncated?: boolean;
  complete?: boolean;
  external_imports?: { total: number; packages: string[] };
}

export interface MapResponse {
  parent: string;
  items: StudioItem[];
  groups: StudioItem[];
  edges: StudioEdge[];
  next_cursor: string | null;
  coverage?: StudioCoverage;
  module_overview?: boolean;
  module_total?: number | null;
  scope_truncated?: boolean;
  edges_truncated?: boolean;
}

export interface CallResolutionArtifact {
  language: string;
  index_sha256: string;
  manifest_sha256: string | null;
}

export interface CallResolutionCount {
  language: string;
  status: string;
  provenance: string | null;
  reason: string | null;
  count: number;
}

export interface CallResolutionItem {
  call_id: string;
  relation_id: string;
  language: string;
  status: string;
  provenance: string | null;
  reason: string | null;
  canonical_target_definition_id: string | null;
  target_element_id: string | null;
  dispatch_kind: string | null;
  declaration_path: string | null;
  declaration_line: number | null;
  crate_name: string | null;
  crate_version: string | null;
  symbol_path: string | null;
  reference: { path: string; start_line: number; start_column: number; end_line: number; end_column: number } | null;
}

export interface CallResolutionResponse {
  available: boolean;
  artifacts: CallResolutionArtifact[];
  counts: CallResolutionCount[];
  items: CallResolutionItem[];
  next_cursor: string | null;
}
