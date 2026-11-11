// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The UML Target of `declarations.uml` (`TargetDefinition` and its parts in
//! `ir/architecture_graph.py`).

use crate::model::{DecidedBy, ItemId};

closed_enum!(EntityKind {
    Component,
    Package,
    Module,
    Class,
    Interface,
    Enum,
    Mixin,
    EnumLiteral,
    Method,
    Function,
    Attribute,
    TypeAlias,
    Constant,
    Macro,
    Binding,
    Symbol,
});

closed_enum!(
    /// The version of the graph schema. Its order is the order of the schema evolution.
    GraphSchemaVersion {
        #[serde(rename = "1.0.0")]
        V1_0,
        #[serde(rename = "1.1.0")]
        V1_1,
        #[serde(rename = "1.2.0")]
        V1_2,
        #[serde(rename = "1.3.0")]
        V1_3,
    }
);

closed_enum!(RelationshipKind {
    Imports,
    Calls,
    References,
    Inherits,
    Realizes,
    MixesIn,
    Creates,
    InstanceOf,
    Owns,
    Requires,
    Publishes,
});

closed_enum!(VisibilityKind {
    Public,
    Private,
    Protected,
    Package,
    Unknown,
});

closed_enum!(VisibilityBasis {
    Language,
    Convention,
    Declared,
    Unknown,
});

closed_enum!(ModifierKind {
    Abstract,
    Static,
    Class,
    Async,
    Frozen,
    Mixin,
});

closed_enum!(PresenceKind {
    Defined,
    Referenced,
    Planned,
    Unspecified,
});

closed_enum!(ResolutionKind {
    Resolved,
    Partial,
    Unresolved,
    NotApplicable,
});

closed_enum!(CompletenessMode { Open, Closed });

closed_enum!(ParameterKind {
    PositionalOnly,
    Positional,
    KeywordOnly,
    Varargs,
    Kwargs,
    Unknown,
});

closed_enum!(DefinitionContextKind {
    If,
    For,
    AsyncFor,
    While,
    Try,
    TryStar,
    With,
    AsyncWith,
    Match,
});

closed_enum!(DefinitionBranchKind {
    Body,
    Else,
    Handler,
    Finally,
    Case,
});

record!(pub(crate), Visibility {
    kind: VisibilityKind,
    basis: VisibilityBasis,
    spelling: Option<String>,
});

record!(pub(crate), Parameter {
    name: String,
    annotation: Option<String>,
    kind: ParameterKind,
    default: Option<String>,
    default_known: bool,
});

record!(pub(crate), Signature {
    parameters: Vec<Parameter>,
    returns: Option<String>,
});

record!(pub(crate), DefinitionContext {
    kind: DefinitionContextKind,
    branch: DefinitionBranchKind,
    evidence_ids: Vec<ItemId>,
});

record!(
    pub(crate),
    /// One element of the Target: a component, a classifier, an operation or another kind.
    Entity {
        id: ItemId,
        kind: EntityKind,
        qualified_name: String,
        language: String,
        parent_id: Option<ItemId>,
        visibility: Visibility,
        signature: Option<Signature>,
        annotation: Option<String>,
        modifiers: Vec<ModifierKind>,
        presence: PresenceKind,
        responsibilities: Vec<String>,
        evidence_ids: Vec<ItemId>,
        provenance: Vec<String>,
        record_ids: Vec<ItemId>,
        definition_contexts: Vec<DefinitionContext>,
        initializer: Option<String>,
        file_path: Option<String>,
    }
);

record!(
    pub(crate),
    /// One relationship of the Target.
    Relationship {
        id: ItemId,
        kind: RelationshipKind,
        source_id: ItemId,
        target_id: Option<ItemId>,
        resolution: ResolutionKind,
        candidate_ids: Vec<ItemId>,
        expression: Option<String>,
        evidence_ids: Vec<ItemId>,
        provenance: Vec<String>,
        record_ids: Vec<ItemId>,
        candidate_count: Option<u64>,
        candidates_truncated: bool,
        reason: Option<String>,
        through: Vec<String>,
        decided_by: Option<DecidedBy>,
    }
);

record!(
    pub(crate),
    /// A completeness scope of the Target.
    TargetScope {
        scope_id: ItemId,
        mode: CompletenessMode,
        rationale: String,
        provenance: Vec<String>,
        entity_kinds: Vec<EntityKind>,
        relationship_kinds: Vec<RelationshipKind>,
    }
);

record!(
    pub(crate),
    /// The UML Target of a contract.
    Target {
        entities: Vec<Entity>,
        relationships: Vec<Relationship>,
        scopes: Vec<TargetScope>,
        schema_version: GraphSchemaVersion,
    }
);
