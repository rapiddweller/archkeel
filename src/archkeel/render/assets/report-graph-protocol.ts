// Native graph scene values. Wire vocabularies are generated from Python owners.
namespace ArchkeelGraphSceneProtocol {
  import G = ArchkeelGraphProtocol;
  export enum ViewMode {
    DIAGRAM = "diagram", TARGET = "target", DIFF = "diff",
    ACTUAL = "actual", STRUCTURE = "structure", REVIEW = "review"
  }
  export type ProjectionMode = ViewMode.DIAGRAM | ViewMode.TARGET | ViewMode.DIFF;
  export function projectViewMode(value: ViewMode): ProjectionMode {
    switch (value) {
      case ViewMode.ACTUAL:
      case ViewMode.STRUCTURE:
      case ViewMode.REVIEW: return ViewMode.DIAGRAM;
      default: return value;
    }
  }
  export enum EdgeState {
    OBSERVED = "observed", DECLARED = "declared", VIOLATION = "violation", UNDECIDED = "undecided"
  }
  export enum SceneEdgeKind { DEPENDENCY = "dependency" }
  export enum ModuleFileKind { NAMED, PYTHON_INITIALIZER }
  const moduleEntryNames: ReadonlyMap<unknown, ModuleFileKind> = new Map([
    ["__init__.py", ModuleFileKind.PYTHON_INITIALIZER],
  ]);
  export function classifyModuleFileName(name: string): ModuleFileKind {
    return moduleEntryNames.get(name) ?? ModuleFileKind.NAMED;
  }
  enum JavaScriptType { OBJECT = "object", STRING = "string", BOOLEAN = "boolean" }
  const views: ReadonlyMap<unknown, ViewMode> = new Map(
    Object.values(ViewMode).map((value): [unknown, ViewMode] => [value, value]),
  );
  export function decodeViewMode(value: unknown): ViewMode {
    const token = views.get(value);
    if (token === undefined) throw new TypeError("Unsupported scene view");
    return token;
  }
  export interface Parameter {
    name: string; kind: G.ParameterKind; annotation?: string | null;
    default?: string | null; default_known?: boolean;
  }
  export interface Signature { parameters: Parameter[]; returns?: string | null }
  export interface Entity {
    id: string; kind: G.EntityKind; qualified_name: string; parent_id: string | null;
    presence: G.PresenceKind; responsibilities: string[]; modifiers: G.ModifierKind[];
    visibility?: {kind: G.VisibilityKind}; signature?: Signature | null;
    annotation?: string | null; initializer?: string | null; file_path?: string | null;
  }
  export interface Relationship {
    id: string; kind: G.RelationshipKind; source_id: string; target_id: string | null;
    candidate_ids: string[]; resolution: G.ResolutionKind;
  }
  export interface ComponentIntent {
    component_id: string; role?: G.ComponentRole; parent_id?: string | null; label?: string | null;
  }
  export interface Graph {
    origin: G.OriginKind; entities: Entity[]; relationships: Relationship[];
    component_intents?: ComponentIntent[]; schema_version?: G.GraphSchemaVersion;
  }
  export interface Assessment {
    id: string; subject_id: string; observed_ids: string[];
    status: G.AssessmentStatus; change?: G.AssessmentChange;
  }
  export interface Comparison {
    assessments: Assessment[];
    correspondences?: {target_id: string; observed_ids: string[]}[];
  }
  export interface Finding {
    graph_subject_ids: string[]; status: G.AssessmentStatus;
  }
  export interface DecisionGap { relationship_ids: string[] }
  export interface Report {
    observed?: Graph | null; target?: Graph | null;
    memberships?: {component_id: string; module_ids: string[]}[];
    findings?: Finding[]; decision_gaps?: DecisionGap[]; comparison?: Comparison | null;
  }
  export interface Context { graph: Graph; scope: string | null; comparison?: Comparison | null }
  export interface Options { viewMode?: ViewMode; directChildren?: boolean }
  export interface GraphIndex {
    entities: Entity[]; byId: Map<string, Entity>;
    parents: Map<string, string | null>; children: Map<string | null, Entity[]>;
    comparison?: Comparison | null;
  }
  export interface Entry { id: string; entity: Entity; sourceGraph: Graph; local: boolean }
  export interface Section { label: string; lines: {text: string; static: boolean}[] }
  export interface SceneNode {
    id: string; kind: G.EntityKind; entity: Entity; sourceGraph: Graph;
    assessments: Assessment[]; observedCounterpart: Entity | null;
    label: string; meta: string; sections: Section[];
    memberCounts: {literals: number; fields: number; methods: number};
    outside: boolean; tooltip: string;
  }
  export interface EdgeGroup {
    id: string; source: string; target: string; kind: SceneEdgeKind;
    relationshipKind: G.RelationshipKind; resolution: G.ResolutionKind;
    sites: Relationship[]; sourceGraph: Graph; assessments: Assessment[]; state: EdgeState;
  }
  export interface SceneEdge extends EdgeGroup {
    observedSites: Relationship[]; findings: Finding[]; decisionGaps: DecisionGap[]; tooltip: string;
  }
  export interface Scene {
    nodes: SceneNode[]; frames: never[]; edges: SceneEdge[];
    owner: string | null; componentOverview: boolean;
  }
  export function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === JavaScriptType.OBJECT && value !== null && !Array.isArray(value);
  }
  function isText(value: unknown): value is string {
    return typeof value === JavaScriptType.STRING;
  }
  function isNullableText(value: unknown): value is string | null {
    return value === null || isText(value);
  }
  function isOptionalText(value: unknown): value is string | null | undefined {
    return value === undefined || isNullableText(value);
  }
  function isList(value: unknown): value is unknown[] { return Array.isArray(value); }
  function isTexts(value: unknown): value is string[] {
    return isList(value) && value.every(isText);
  }
  function isParameter(value: unknown): value is Parameter {
    return isRecord(value) && isText(value.name) && G.isParameterKind(value.kind)
      && isOptionalText(value.annotation) && isOptionalText(value.default)
      && (value.default_known === undefined || typeof value.default_known === JavaScriptType.BOOLEAN);
  }
  function isSignature(value: unknown): value is Signature {
    return isRecord(value) && isList(value.parameters) && value.parameters.every(isParameter)
      && isOptionalText(value.returns);
  }
  function isEntity(value: unknown): value is Entity {
    return isRecord(value) && isText(value.id) && G.isEntityKind(value.kind)
      && isText(value.qualified_name) && isNullableText(value.parent_id)
      && G.isPresenceKind(value.presence) && isTexts(value.responsibilities)
      && isList(value.modifiers) && value.modifiers.every(G.isModifierKind)
      && (value.visibility === undefined || isRecord(value.visibility)
        && G.isVisibilityKind(value.visibility.kind))
      && (value.signature === undefined || value.signature === null || isSignature(value.signature))
      && isOptionalText(value.annotation) && isOptionalText(value.initializer)
      && isOptionalText(value.file_path);
  }
  function isRelationship(value: unknown): value is Relationship {
    return isRecord(value) && isText(value.id) && G.isRelationshipKind(value.kind)
      && isText(value.source_id) && isNullableText(value.target_id)
      && isTexts(value.candidate_ids) && G.isResolutionKind(value.resolution);
  }
  function isIntent(value: unknown): value is ComponentIntent {
    return isRecord(value) && isText(value.component_id)
      && (value.role === undefined || G.isComponentRole(value.role))
      && isOptionalText(value.parent_id) && isOptionalText(value.label);
  }
  function isGraph(value: unknown): value is Graph {
    return isRecord(value) && G.isOriginKind(value.origin)
      && isList(value.entities) && value.entities.every(isEntity)
      && isList(value.relationships) && value.relationships.every(isRelationship)
      && (value.component_intents === undefined || isList(value.component_intents)
        && value.component_intents.every(isIntent))
      && (value.schema_version === undefined || G.isGraphSchemaVersion(value.schema_version));
  }
  function isAssessment(value: unknown): value is Assessment {
    return isRecord(value) && isText(value.id) && isText(value.subject_id)
      && isTexts(value.observed_ids) && G.isAssessmentStatus(value.status)
      && (value.change === undefined || G.isAssessmentChange(value.change));
  }
  function isCorrespondence(value: unknown): value is {target_id: string; observed_ids: string[]} {
    return isRecord(value) && isText(value.target_id) && isTexts(value.observed_ids);
  }
  function isComparison(value: unknown): value is Comparison {
    return isRecord(value) && isList(value.assessments) && value.assessments.every(isAssessment)
      && (value.correspondences === undefined || isList(value.correspondences)
        && value.correspondences.every(isCorrespondence));
  }
  function isMembership(value: unknown): value is {component_id: string; module_ids: string[]} {
    return isRecord(value) && isText(value.component_id) && isTexts(value.module_ids);
  }
  function isFinding(value: unknown): value is Finding {
    return isRecord(value) && isTexts(value.graph_subject_ids) && G.isAssessmentStatus(value.status);
  }
  function isGap(value: unknown): value is DecisionGap {
    return isRecord(value) && isTexts(value.relationship_ids);
  }
  function isReport(value: unknown): value is Report {
    return isRecord(value)
      && (value.observed === undefined || value.observed === null || isGraph(value.observed))
      && (value.target === undefined || value.target === null || isGraph(value.target))
      && (value.memberships === undefined || isList(value.memberships) && value.memberships.every(isMembership))
      && (value.findings === undefined || isList(value.findings) && value.findings.every(isFinding))
      && (value.decision_gaps === undefined || isList(value.decision_gaps) && value.decision_gaps.every(isGap))
      && (value.comparison === undefined || value.comparison === null || isComparison(value.comparison));
  }
  export interface AtlasDeviation {
    id: string; kind: G.AtlasDeviationKind; source_id: string; target_id: string;
    level_id: string | null;
  }
  function isAtlasDeviation(value: unknown): value is AtlasDeviation {
    return isRecord(value) && isText(value.id) && G.isAtlasDeviationKind(value.kind)
      && isText(value.source_id) && isText(value.target_id) && isNullableText(value.level_id);
  }
  export function decodeAtlasDeviations(value: unknown): AtlasDeviation[] {
    if (!isList(value) || !value.every(isAtlasDeviation)) throw new TypeError("Unsupported Atlas deviations");
    return value;
  }
  export function decodeReport(value: unknown): Report {
    if (!isReport(value)) throw new TypeError("Unsupported native graph scene report");
    return value;
  }
  export function decodeGraph(value: unknown): Graph {
    if (!isGraph(value)) throw new TypeError("Unsupported native graph scene graph");
    return value;
  }
  export function decodeComparison(value: unknown): Comparison | null {
    if (value === null || value === undefined) return null;
    if (!isComparison(value)) throw new TypeError("Unsupported native graph scene comparison");
    return value;
  }
}
