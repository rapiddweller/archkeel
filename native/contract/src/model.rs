// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed and closed contract. Each type holds what the Python dataclass of the same name in
//! `ir/model.py` holds, so the canonical bytes come from the same values.
//!
//! The fields are private to the crate and each has a read accessor. So a `Contract` and each value
//! in it come only from `parse`: a caller cannot build or change one.

pub(crate) use crate::macros::{wrap_all, Wrap};

text_type!(
    pub(crate),
    /// The id of a contract item: a component or a rule.
    ItemId
);
text_type!(
    pub(crate),
    /// The label of a component. A `requires` entry and a rule name a component by its label.
    ComponentLabel
);
text_type!(
    pub(crate),
    /// A package or a module that a component owns: dotted names.
    Package
);
text_type!(
    pub(crate),
    /// A module selector of a rule or of an interface: a prefix, an exact module or `module:Name`.
    Selector
);
text_type!(
    pub(crate),
    /// The repository path of an inside contract that a component mounts (AD-20).
    InsidePath
);
text_type!(
    pub(crate),
    /// A repository-relative source path.
    SourcePath
);
text_type!(
    pub(crate),
    /// The SHA-256 of bytes in lower-case hex.
    ContractDigest
);

closed_enum!(
    /// Who decided a component, an edge or a rule.
    DecidedBy {
        /// The architect decided it.
        Architect,
        /// An agent decided it.
        Agent,
    }
);

closed_enum!(
    /// What a component is for.
    ComponentRole {
        /// An ordinary component.
        Component,
        /// An interface that others import.
        Interface,
        /// A contract that others follow.
        Contract,
        /// A view of another component.
        Projection,
        /// A base that every component may use.
        Foundation,
    }
);

closed_enum!(
    /// A planned component owns no module yet.
    Lifecycle {
        /// The component is planned.
        Planned,
    }
);

record!(
    pub(crate),
    /// One component that its owner can import, and the reason (AD-32).
    Requirement {
        /// The component that may be imported.
        component: ComponentLabel,
        /// Why the item exists, as the contract states it.
        rationale: String,
        /// The selectors that the import must pass through.
        through: Vec<Selector>,
        /// Who decided it.
        #[serde(skip_serializing_if = "Option::is_none")]
        decided_by: Option<DecidedBy>,
    }
);

record!(
    pub(crate),
    /// One component. An absent optional field stays absent in the canonical bytes.
    Component {
        /// The id of the component.
        id: ItemId,
        /// The name that a person reads.
        label: ComponentLabel,
        /// The role that the rule reads.
        role: ComponentRole,
        /// The packages that the component owns.
        packages: Vec<Package>,
        /// What the element is responsible for.
        responsibilities: Vec<String>,
        /// What the component must not do.
        forbidden_responsibilities: Vec<String>,
        /// Where the item comes from.
        provenance: Vec<String>,
        /// The id of the capability that the component serves.
        #[serde(skip_serializing_if = "Option::is_none")]
        capability_id: Option<ItemId>,
        /// The components that this one may import.
        #[serde(skip_serializing_if = "Option::is_none")]
        requires: Option<Vec<Requirement>>,
        /// The path of the inside contract of the component.
        #[serde(skip_serializing_if = "Option::is_none")]
        inside: Option<InsidePath>,
        /// The selectors of the public surface.
        #[serde(skip_serializing_if = "Option::is_none")]
        public: Option<Vec<Selector>>,
        /// The selectors of the planned surface.
        #[serde(skip_serializing_if = "Option::is_none")]
        planned: Option<Vec<Selector>>,
        /// Who decided it.
        #[serde(skip_serializing_if = "Option::is_none")]
        decided_by: Option<DecidedBy>,
        /// The namespace of the component.
        #[serde(skip_serializing_if = "Option::is_none")]
        namespace: Option<Package>,
        /// Empty when the contract declares no exact module.
        #[serde(skip_serializing_if = "Vec::is_empty")]
        exact_modules: Vec<Package>,
        /// The layer of the component.
        #[serde(skip_serializing_if = "Option::is_none")]
        layer: Option<String>,
        /// The lifecycle of the component.
        #[serde(skip_serializing_if = "Option::is_none")]
        lifecycle: Option<Lifecycle>,
    }
);

closed_enum!(
    /// The 23 rule kinds of the grammar (`ArchitectureRuleKind`).
    RuleKind {
        /// A rule on who may call a target.
        CallOwner,
        /// A rule on an argument that no call may pass.
        ForbiddenCallArgument,
        /// A rule on an argument that a catalog limits.
        CatalogArgument,
        /// A rule on the use of a catalog value.
        CatalogUse,
        /// A rule on an effect that a condition forbids.
        ForbiddenEffectUnderCondition,
        /// A rule on an import that is forbidden.
        ForbiddenDependency,
        /// A rule on an import that is allowed.
        AllowedDependency,
        /// A rule on a written construct that is forbidden.
        ForbiddenConstruct,
        /// A rule on who owns a source value.
        SourceOwnership,
        /// A rule on where an external dependency may be imported.
        ExternalDependencyScope,
        /// A rule that each module has one owner.
        CompleteAssignment,
        /// A rule on the children of a root.
        RootLayout,
        /// A rule that each external import is declared.
        CompleteExternalScope,
        /// A rule that each import is a declared requirement.
        CompleteRequires,
        /// A rule on the order of layers.
        LayerOrder,
        /// A rule that no cycle exists.
        NoComponentCycles,
        /// A rule on what an interface exposes.
        InterfaceBoundary,
        /// A rule that siblings do not import each other.
        SiblingIsolation,
        /// A rule on where a kind of class may live.
        SymbolPlacement,
        /// A rule on the types at a boundary.
        BoundaryTypes,
        /// A rule on a bounded numeric operand.
        BoundedNumericOperand,
        /// A rule on the declarations of a protocol.
        ProtocolDeclarations,
        /// A rule that each public name of a component has a user in another component.
        UnusedPublic,
    }
);

record!(
    pub(crate),
    /// The fields that each rule holds.
    RuleHead {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// Why the item exists, as the contract states it.
        rationale: String,
        /// Where the item comes from.
        provenance: Vec<String>,
        /// Who decided it.
        decided_by: DecidedBy,
    }
);

closed_enum!(
    /// How a selector matches a name.
    SelectorMatch {
        /// The selector matches the name and what is below it.
        Prefix,
        /// The selector matches the name only.
        Exact,
    }
);

closed_enum!(
    /// What the target of a dependency rule is.
    TargetKind {
        /// A module.
        Module,
        /// The namespace that an import binds.
        ImportNamespace,
    }
);

record!(
    pub(crate),
    /// A rule that forbids an import of the target.
    ForbiddenDependency {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The selector of the modules that the rule names as the other side.
        target: Selector,
        /// True when an import under `TYPE_CHECKING` counts.
        include_type_checking: bool,
        /// The imported name that the rule forbids.
        #[serde(skip_serializing_if = "Option::is_none")]
        target_symbol: Option<String>,
        /// True when the rule reads written names, not inferred receiver types or execution.
        #[serde(skip_serializing_if = "is_false")]
        source_symbol_only: bool,
        /// The sources that the rule excepts by prefix.
        allowed_sources: Vec<Selector>,
        /// Whether the source selector matches by prefix or by exact name.
        #[serde(skip_serializing_if = "is_prefix")]
        source_match: SelectorMatch,
        /// Whether the target selector matches by prefix or by exact name.
        #[serde(skip_serializing_if = "is_prefix")]
        target_match: SelectorMatch,
        /// Whether the target is a module or an import namespace.
        #[serde(skip_serializing_if = "is_module")]
        target_kind: TargetKind,
        /// True when a path of imports through other modules also breaks the rule.
        #[serde(skip_serializing_if = "is_false")]
        indirect: bool,
    }
);

record!(
    pub(crate),
    /// A rule that allows an import of the target.
    AllowedDependency {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The selector of the modules that the rule names as the other side.
        target: Selector,
    }
);

record!(
    pub(crate),
    /// A rule on where an external dependency may be imported.
    ExternalDependencyScope {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The external dependency that the rule names.
        dependency: Selector,
        /// The sources that the rule excepts by prefix.
        allowed_sources: Vec<Selector>,
        /// The sources that the rule excepts by exact name.
        exact_sources: Vec<Selector>,
    }
);

record!(
    pub(crate),
    /// `complete_assignment` and `complete_external_scope`: a rule over one source prefix.
    SourceRule {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
    }
);

record!(
    pub(crate),
    /// A rule on the children of a root.
    RootLayout {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The root contract.
        root: Selector,
        /// The children that the root may have.
        allowed_children: Vec<Selector>,
    }
);

record!(
    pub(crate),
    /// A rule that each import is a declared requirement.
    CompleteRequires {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// True when an import under `TYPE_CHECKING` counts.
        include_type_checking: bool,
    }
);

record!(
    pub(crate),
    /// A rule on the order of layers.
    LayerOrder {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The layers from top to bottom.
        layers: Vec<String>,
        /// The components that the rule names.
        #[serde(skip_serializing_if = "Option::is_none")]
        components: Option<Vec<ComponentLabel>>,
    }
);

closed_enum!(
    /// The level at which a cycle rule looks.
    CycleLevel {
        /// The cycles between components.
        Component,
        /// The cycles between modules.
        Module,
    }
);

record!(
    pub(crate),
    /// A rule that no cycle exists.
    NoComponentCycles {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The level at which the rule looks for cycles.
        #[serde(skip_serializing_if = "is_component")]
        level: CycleLevel,
        /// The components that the rule names.
        #[serde(skip_serializing_if = "Option::is_none")]
        components: Option<Vec<ComponentLabel>>,
    }
);

record!(
    pub(crate),
    /// One exact caller module can import one exact module object.
    ModuleObjectGrant {
        /// The module that holds the import.
        source_module: Selector,
        /// The module that the import reaches.
        target_module: Selector,
    }
);

record!(
    pub(crate),
    /// A rule on what an interface exposes.
    InterfaceBoundary {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// True when an import under `TYPE_CHECKING` counts.
        include_type_checking: bool,
        /// The module objects that the interface may expose.
        #[serde(skip_serializing_if = "Option::is_none")]
        module_object_grants: Option<Vec<ModuleObjectGrant>>,
    }
);

record!(
    pub(crate),
    /// A rule that siblings do not import each other.
    SiblingIsolation {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The members that the rule names.
        members: Vec<Selector>,
        /// True when an import under `TYPE_CHECKING` counts.
        include_type_checking: bool,
    }
);

/// The defaults that the canonical bytes leave out: an absent permission keeps the amendment
/// digests of older contracts.
fn is_prefix(value: &SelectorMatch) -> bool {
    *value == SelectorMatch::Prefix
}

fn is_module(value: &TargetKind) -> bool {
    *value == TargetKind::Module
}

/// Omit an inactive rule option to preserve canonical bytes.
pub(crate) fn is_false(value: &bool) -> bool {
    !*value
}

fn is_component(value: &CycleLevel) -> bool {
    *value == CycleLevel::Component
}
