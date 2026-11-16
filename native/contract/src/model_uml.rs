// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The UML Target of `declarations.uml` (`TargetDefinition` and its parts in
//! `ir/architecture_graph.py`).

use crate::model::{DecidedBy, ItemId, Selector};

closed_enum!(
    /// The kind of an entity of the target model.
    EntityKind {
        /// A component.
        Component,
        /// A package.
        Package,
        /// A module.
        Module,
        /// A class.
        Class,
        /// An interface.
        Interface,
        /// An enum.
        Enum,
        /// A mixin.
        Mixin,
        /// A literal of an enum.
        EnumLiteral,
        /// A method.
        Method,
        /// A function.
        Function,
        /// An attribute.
        Attribute,
        /// A type alias.
        TypeAlias,
        /// A constant.
        Constant,
        /// A macro.
        Macro,
        /// A binding.
        Binding,
        /// A symbol of another kind.
        Symbol,
    }
);

closed_enum!(
    /// The version of the graph schema. Its order is the order of the schema evolution.
    GraphSchemaVersion {
        /// Graph schema 1.0.0.
        #[serde(rename = "1.0.0")]
        V1_0,
        /// Graph schema 1.1.0.
        #[serde(rename = "1.1.0")]
        V1_1,
        /// Graph schema 1.2.0.
        #[serde(rename = "1.2.0")]
        V1_2,
        /// Graph schema 1.3.0.
        #[serde(rename = "1.3.0")]
        V1_3,
    }
);

closed_enum!(
    /// The kind of a relationship between two entities.
    RelationshipKind {
        /// The source imports the target.
        Imports,
        /// The source calls the target.
        Calls,
        /// The source refers to the target.
        References,
        /// The source inherits from the target.
        Inherits,
        /// The source realizes the target.
        Realizes,
        /// The source mixes in the target.
        MixesIn,
        /// The source creates the target.
        Creates,
        /// The source is an instance of the target.
        InstanceOf,
        /// The source owns the target.
        Owns,
        /// The source requires the target.
        Requires,
        /// The source publishes the target.
        Publishes,
    }
);

closed_enum!(
    /// How visible an element is.
    VisibilityKind {
        /// Public.
        Public,
        /// Private.
        Private,
        /// Protected.
        Protected,
        /// Visible in the package.
        Package,
        /// Not known.
        Unknown,
    }
);

closed_enum!(
    /// Why an element has its visibility.
    VisibilityBasis {
        /// The language fixes it.
        Language,
        /// A naming convention sets it.
        Convention,
        /// The contract declares it.
        Declared,
        /// Not known.
        Unknown,
    }
);

closed_enum!(
    /// A modifier of an element.
    ModifierKind {
        /// Abstract.
        Abstract,
        /// Static.
        Static,
        /// Of the class.
        Class,
        /// Asynchronous.
        Async,
        /// Frozen.
        Frozen,
        /// A mixin.
        Mixin,
    }
);

closed_enum!(
    /// Whether an element exists.
    PresenceKind {
        /// The code defines it.
        Defined,
        /// The code only refers to it.
        Referenced,
        /// The contract plans it.
        Planned,
        /// Not stated.
        Unspecified,
    }
);

closed_enum!(
    /// How far a relationship is resolved.
    ResolutionKind {
        /// The target is proven.
        Resolved,
        /// The target is partly proven.
        Partial,
        /// No target is proven.
        Unresolved,
        /// The relationship needs no resolution.
        NotApplicable,
    }
);

closed_enum!(
    /// Whether a scope lists every element.
    CompletenessMode {
        /// Other elements may exist.
        Open,
        /// No other element exists.
        Closed,
    }
);

closed_enum!(
    /// The kind of a parameter.
    ParameterKind {
        /// Positional only.
        PositionalOnly,
        /// Positional or keyword.
        Positional,
        /// Keyword only.
        KeywordOnly,
        /// Collects extra positional arguments.
        Varargs,
        /// Collects extra keyword arguments.
        Kwargs,
        /// Not known.
        Unknown,
    }
);

closed_enum!(
    /// The statement that holds a definition.
    DefinitionContextKind {
        /// An `if` statement.
        If,
        /// A `for` statement.
        For,
        /// An `async for` statement.
        AsyncFor,
        /// A `while` statement.
        While,
        /// A `try` statement.
        Try,
        /// A `try` statement with `except*`.
        TryStar,
        /// A `with` statement.
        With,
        /// An `async with` statement.
        AsyncWith,
        /// A `match` statement.
        Match,
    }
);

closed_enum!(
    /// The branch of a statement that holds a definition.
    DefinitionBranchKind {
        /// The body.
        Body,
        /// The `else` branch.
        Else,
        /// An exception handler.
        Handler,
        /// The `finally` branch.
        Finally,
        /// A `case` branch.
        Case,
    }
);

record!(
    pub(crate),
    /// The visibility of an element and why it holds.
    Visibility {
        /// How visible the element is.
        kind: VisibilityKind,
        /// Why the element has this visibility.
        basis: VisibilityBasis,
        /// The name as written, which can decide the visibility.
        spelling: Option<String>,
    }
);

record!(
    pub(crate),
    /// One parameter of a callable.
    Parameter {
        /// The name as written.
        name: String,
        /// The annotation as written.
        annotation: Option<String>,
        /// The kind of the parameter.
        kind: ParameterKind,
        /// The default value as written.
        default: Option<String>,
        /// True when the default is read.
        default_known: bool,
    }
);

record!(
    pub(crate),
    /// The signature of a callable.
    Signature {
        /// The parameters that the rule names.
        parameters: Vec<Parameter>,
        /// The return annotation as written.
        returns: Option<String>,
    }
);

record!(
    pub(crate),
    /// One statement that holds a definition.
    DefinitionContext {
        /// The kind of the statement.
        kind: DefinitionContextKind,
        /// The branch of the statement.
        branch: DefinitionBranchKind,
        /// The ids of the evidence that backs the item.
        evidence_ids: Vec<ItemId>,
    }
);

record!(
    pub(crate),
    /// One element of the Target: a component, a classifier, an operation or another kind.
    Entity {
        /// The id of the entity.
        id: ItemId,
        /// The kind of the entity.
        kind: EntityKind,
        /// The qualified name of the symbol.
        qualified_name: String,
        /// The language of the element.
        language: String,
        /// The id of the parent element.
        parent_id: Option<ItemId>,
        /// The visibility of the member.
        visibility: Visibility,
        /// The signature of the callable.
        signature: Option<Signature>,
        /// The annotation as written.
        annotation: Option<String>,
        /// The modifiers of the element.
        modifiers: Vec<ModifierKind>,
        /// Whether the element is defined, referenced or planned.
        presence: PresenceKind,
        /// What the element is responsible for.
        responsibilities: Vec<String>,
        /// The ids of the evidence that backs the item.
        evidence_ids: Vec<ItemId>,
        /// Where the item comes from.
        provenance: Vec<String>,
        /// The ids of the fact records that back the item.
        record_ids: Vec<ItemId>,
        /// The places where the element is defined.
        definition_contexts: Vec<DefinitionContext>,
        /// The initializer as written.
        initializer: Option<String>,
        /// The file that holds the element.
        file_path: Option<String>,
    }
);

record!(
    pub(crate),
    /// One relationship of the Target.
    Relationship {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The kind of the relationship.
        kind: RelationshipKind,
        /// The id of the element where the relationship starts.
        source_id: ItemId,
        /// The id of the element where the relationship ends.
        target_id: Option<ItemId>,
        /// How far the relationship is resolved.
        resolution: ResolutionKind,
        /// The ids of the targets that the item can resolve to.
        candidate_ids: Vec<ItemId>,
        /// The expression as written.
        expression: Option<String>,
        /// The ids of the evidence that backs the item.
        evidence_ids: Vec<ItemId>,
        /// Where the item comes from.
        provenance: Vec<String>,
        /// The ids of the fact records that back the item.
        record_ids: Vec<ItemId>,
        /// How many targets the item can resolve to.
        candidate_count: Option<u64>,
        /// True when the list of candidates is cut.
        candidates_truncated: bool,
        /// Why it holds or fails.
        reason: Option<String>,
        /// The selectors that the import must pass through.
        through: Vec<Selector>,
        /// Who decided it.
        decided_by: Option<DecidedBy>,
    }
);

record!(
    pub(crate),
    /// A completeness scope of the Target.
    TargetScope {
        /// The id of the scope.
        scope_id: ItemId,
        /// Whether the scope is open or closed.
        mode: CompletenessMode,
        /// Why the item exists, as the contract states it.
        rationale: String,
        /// Where the item comes from.
        provenance: Vec<String>,
        /// The entity kinds that the scope covers.
        entity_kinds: Vec<EntityKind>,
        /// The relationship kinds that the scope covers.
        relationship_kinds: Vec<RelationshipKind>,
    }
);

record!(
    pub(crate),
    /// The UML Target of a contract.
    Target {
        /// The entities that the target declares.
        entities: Vec<Entity>,
        /// The relationships that the target declares.
        relationships: Vec<Relationship>,
        /// The scopes that the target declares.
        scopes: Vec<TargetScope>,
        /// The version of the graph schema.
        schema_version: GraphSchemaVersion,
    }
);
