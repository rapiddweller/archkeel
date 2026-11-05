declare namespace ArchkeelGraphProtocol {
    enum AtlasDeviationKind {
        ALLOWED_UNUSED = "allowed_unused",
        UNDECLARED = "undeclared"
    }
    function isAtlasDeviationKind(value: unknown): value is AtlasDeviationKind;
    enum OriginKind {
        OBSERVED = "observed",
        DECLARED = "declared"
    }
    function isOriginKind(value: unknown): value is OriginKind;
    enum EntityKind {
        COMPONENT = "component",
        PACKAGE = "package",
        MODULE = "module",
        CLASS = "class",
        INTERFACE = "interface",
        ENUM = "enum",
        MIXIN = "mixin",
        ENUM_LITERAL = "enum_literal",
        METHOD = "method",
        FUNCTION = "function",
        ATTRIBUTE = "attribute",
        TYPE_ALIAS = "type_alias",
        CONSTANT = "constant",
        BINDING = "binding",
        SYMBOL = "symbol"
    }
    function isEntityKind(value: unknown): value is EntityKind;
    enum RelationshipKind {
        IMPORTS = "imports",
        CALLS = "calls",
        REFERENCES = "references",
        INHERITS = "inherits",
        REALIZES = "realizes",
        MIXES_IN = "mixes_in",
        CREATES = "creates",
        INSTANCE_OF = "instance_of",
        OWNS = "owns",
        REQUIRES = "requires",
        PUBLISHES = "publishes"
    }
    function isRelationshipKind(value: unknown): value is RelationshipKind;
    enum PresenceKind {
        DEFINED = "defined",
        REFERENCED = "referenced",
        PLANNED = "planned",
        UNSPECIFIED = "unspecified"
    }
    function isPresenceKind(value: unknown): value is PresenceKind;
    enum ResolutionKind {
        RESOLVED = "resolved",
        PARTIAL = "partial",
        UNRESOLVED = "unresolved",
        NOT_APPLICABLE = "not_applicable"
    }
    function isResolutionKind(value: unknown): value is ResolutionKind;
    enum VisibilityKind {
        PUBLIC = "public",
        PRIVATE = "private",
        PROTECTED = "protected",
        PACKAGE = "package",
        UNKNOWN = "unknown"
    }
    function isVisibilityKind(value: unknown): value is VisibilityKind;
    enum ParameterKind {
        POSITIONAL_ONLY = "positional_only",
        POSITIONAL = "positional",
        KEYWORD_ONLY = "keyword_only",
        VARARGS = "varargs",
        KWARGS = "kwargs",
        UNKNOWN = "unknown"
    }
    function isParameterKind(value: unknown): value is ParameterKind;
    enum ModifierKind {
        ABSTRACT = "abstract",
        STATIC = "static",
        CLASS = "class",
        ASYNC = "async",
        FROZEN = "frozen",
        MIXIN = "mixin"
    }
    function isModifierKind(value: unknown): value is ModifierKind;
    enum ComponentRole {
        COMPONENT = "component",
        INTERFACE = "interface",
        CONTRACT = "contract",
        PROJECTION = "projection",
        FOUNDATION = "foundation"
    }
    function isComponentRole(value: unknown): value is ComponentRole;
    enum AssessmentStatus {
        PASS = "PASS",
        FAIL = "FAIL",
        UNKNOWN = "UNKNOWN"
    }
    function isAssessmentStatus(value: unknown): value is AssessmentStatus;
    enum AssessmentChange {
        MATCHED = "matched",
        MISSING = "missing",
        UNEXPECTED = "unexpected",
        CHANGED = "changed",
        AMBIGUOUS = "ambiguous",
        UNAVAILABLE = "unavailable"
    }
    function isAssessmentChange(value: unknown): value is AssessmentChange;
    enum GraphSchemaVersion {
        V1_3_0 = "1.3.0",
        V1_2_0 = "1.2.0",
        V1_1_0 = "1.1.0",
        V1_0_0 = "1.0.0"
    }
    function isGraphSchemaVersion(value: unknown): value is GraphSchemaVersion;
}
declare namespace ArchkeelGraphSceneProtocol {
    import G = ArchkeelGraphProtocol;
    enum ViewMode {
        DIAGRAM = "diagram",
        TARGET = "target",
        DIFF = "diff",
        ACTUAL = "actual",
        STRUCTURE = "structure",
        REVIEW = "review"
    }
    type ProjectionMode = ViewMode.DIAGRAM | ViewMode.TARGET | ViewMode.DIFF;
    function projectViewMode(value: ViewMode): ProjectionMode;
    enum EdgeState {
        OBSERVED = "observed",
        DECLARED = "declared",
        VIOLATION = "violation",
        UNDECIDED = "undecided"
    }
    enum SceneEdgeKind {
        DEPENDENCY = "dependency"
    }
    enum ModuleFileKind {
        NAMED = 0,
        PYTHON_INITIALIZER = 1
    }
    function classifyModuleFileName(name: string): ModuleFileKind;
    function decodeViewMode(value: unknown): ViewMode;
    interface Parameter {
        name: string;
        kind: G.ParameterKind;
        annotation?: string | null;
        default?: string | null;
        default_known?: boolean;
    }
    interface Signature {
        parameters: Parameter[];
        returns?: string | null;
    }
    interface Entity {
        id: string;
        kind: G.EntityKind;
        qualified_name: string;
        parent_id: string | null;
        presence: G.PresenceKind;
        responsibilities: string[];
        modifiers: G.ModifierKind[];
        visibility?: {
            kind: G.VisibilityKind;
        };
        signature?: Signature | null;
        annotation?: string | null;
        initializer?: string | null;
        file_path?: string | null;
    }
    interface Relationship {
        id: string;
        kind: G.RelationshipKind;
        source_id: string;
        target_id: string | null;
        candidate_ids: string[];
        resolution: G.ResolutionKind;
    }
    interface ComponentIntent {
        component_id: string;
        role?: G.ComponentRole;
        parent_id?: string | null;
        label?: string | null;
    }
    interface Graph {
        origin: G.OriginKind;
        entities: Entity[];
        relationships: Relationship[];
        component_intents?: ComponentIntent[];
        schema_version?: G.GraphSchemaVersion;
    }
    interface Assessment {
        id: string;
        subject_id: string;
        observed_ids: string[];
        status: G.AssessmentStatus;
        change?: G.AssessmentChange;
    }
    interface Comparison {
        assessments: Assessment[];
        correspondences?: {
            target_id: string;
            observed_ids: string[];
        }[];
    }
    interface Finding {
        graph_subject_ids: string[];
        status: G.AssessmentStatus;
    }
    interface DecisionGap {
        relationship_ids: string[];
    }
    interface Report {
        observed?: Graph | null;
        target?: Graph | null;
        memberships?: {
            component_id: string;
            module_ids: string[];
        }[];
        findings?: Finding[];
        decision_gaps?: DecisionGap[];
        comparison?: Comparison | null;
    }
    interface Context {
        graph: Graph;
        scope: string | null;
        comparison?: Comparison | null;
    }
    interface Options {
        viewMode?: ViewMode;
        directChildren?: boolean;
    }
    interface GraphIndex {
        entities: Entity[];
        byId: Map<string, Entity>;
        parents: Map<string, string | null>;
        children: Map<string | null, Entity[]>;
        comparison?: Comparison | null;
    }
    interface Entry {
        id: string;
        entity: Entity;
        sourceGraph: Graph;
        local: boolean;
    }
    interface Section {
        label: string;
        lines: {
            text: string;
            static: boolean;
        }[];
    }
    interface SceneNode {
        id: string;
        kind: G.EntityKind;
        entity: Entity;
        sourceGraph: Graph;
        assessments: Assessment[];
        observedCounterpart: Entity | null;
        label: string;
        meta: string;
        sections: Section[];
        memberCounts: {
            literals: number;
            fields: number;
            methods: number;
        };
        outside: boolean;
        tooltip: string;
    }
    interface EdgeGroup {
        id: string;
        source: string;
        target: string;
        kind: SceneEdgeKind;
        relationshipKind: G.RelationshipKind;
        resolution: G.ResolutionKind;
        sites: Relationship[];
        sourceGraph: Graph;
        assessments: Assessment[];
        state: EdgeState;
    }
    interface SceneEdge extends EdgeGroup {
        observedSites: Relationship[];
        findings: Finding[];
        decisionGaps: DecisionGap[];
        tooltip: string;
    }
    interface Scene {
        nodes: SceneNode[];
        frames: never[];
        edges: SceneEdge[];
        owner: string | null;
        componentOverview: boolean;
    }
    function isRecord(value: unknown): value is Record<string, unknown>;
    interface AtlasDeviation {
        id: string;
        kind: G.AtlasDeviationKind;
        source_id: string;
        target_id: string;
        level_id: string | null;
    }
    function decodeAtlasDeviations(value: unknown): AtlasDeviation[];
    function decodeReport(value: unknown): Report;
    function decodeGraph(value: unknown): Graph;
    function decodeComparison(value: unknown): Comparison | null;
}
export { ArchkeelGraphProtocol, ArchkeelGraphSceneProtocol };
declare global {
  interface Window {
    ArchkeelGraphScene: typeof import("./report-graph-scene.js");
    ArchkeelAtlasDeviations: typeof import("./report-atlas-deviations.js");
  }
}
