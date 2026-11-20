export interface StudioItem {
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
}

export interface StudioEdge {
  id: string;
  source: string;
  target: string | null;
  kind: string;
  resolution: string;
  title?: string;
  expression?: string;
  reason?: string;
  rationale?: string;
  schema?: string;
  aggregate?: boolean;
  count?: number;
  evidence_total?: number;
}

export interface StudioCoverage {
  parts?: { language?: string }[];
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
