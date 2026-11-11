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
        Architect,
        Agent,
    }
);

closed_enum!(ComponentRole {
    Component,
    Interface,
    Contract,
    Projection,
    Foundation,
});

closed_enum!(
    /// A planned component owns no module yet.
    Lifecycle {
        Planned,
    }
);

record!(
    pub(crate),
    /// One component that its owner can import, and the reason (AD-32).
    Requirement {
        component: ComponentLabel,
        rationale: String,
        through: Vec<Selector>,
        #[serde(skip_serializing_if = "Option::is_none")]
        decided_by: Option<DecidedBy>,
    }
);

record!(
    pub(crate),
    /// One component. An absent optional field stays absent in the canonical bytes.
    Component {
        id: ItemId,
        label: ComponentLabel,
        role: ComponentRole,
        packages: Vec<Package>,
        responsibilities: Vec<String>,
        forbidden_responsibilities: Vec<String>,
        provenance: Vec<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        capability_id: Option<ItemId>,
        #[serde(skip_serializing_if = "Option::is_none")]
        requires: Option<Vec<Requirement>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        inside: Option<InsidePath>,
        #[serde(skip_serializing_if = "Option::is_none")]
        public: Option<Vec<Selector>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        planned: Option<Vec<Selector>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        decided_by: Option<DecidedBy>,
        #[serde(skip_serializing_if = "Option::is_none")]
        namespace: Option<Package>,
        /// Empty when the contract declares no exact module.
        #[serde(skip_serializing_if = "Vec::is_empty")]
        exact_modules: Vec<Package>,
        #[serde(skip_serializing_if = "Option::is_none")]
        layer: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        lifecycle: Option<Lifecycle>,
    }
);

closed_enum!(
    /// The 22 rule kinds of the grammar (`ArchitectureRuleKind`).
    RuleKind {
        CallOwner,
        ForbiddenCallArgument,
        CatalogArgument,
        CatalogUse,
        ForbiddenEffectUnderCondition,
        ForbiddenDependency,
        AllowedDependency,
        ForbiddenConstruct,
        SourceOwnership,
        ExternalDependencyScope,
        CompleteAssignment,
        RootLayout,
        CompleteExternalScope,
        CompleteRequires,
        LayerOrder,
        NoComponentCycles,
        InterfaceBoundary,
        SiblingIsolation,
        SymbolPlacement,
        BoundaryTypes,
        BoundedNumericOperand,
        ProtocolDeclarations,
    }
);

record!(
    pub(crate),
    /// The fields that each rule holds.
    RuleHead {
        id: ItemId,
        rationale: String,
        provenance: Vec<String>,
        decided_by: DecidedBy,
    }
);

closed_enum!(SelectorMatch { Prefix, Exact });

closed_enum!(TargetKind {
    Module,
    ImportNamespace,
});

record!(pub(crate), ForbiddenDependency {
    head: RuleHead,
    source: Selector,
    target: Selector,
    include_type_checking: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    target_symbol: Option<String>,
    allowed_sources: Vec<Selector>,
    #[serde(skip_serializing_if = "is_prefix")]
    source_match: SelectorMatch,
    #[serde(skip_serializing_if = "is_prefix")]
    target_match: SelectorMatch,
    #[serde(skip_serializing_if = "is_module")]
    target_kind: TargetKind,
});

record!(
    pub(crate),
    AllowedDependency {
        head: RuleHead,
        source: Selector,
        target: Selector,
    }
);

closed_enum!(
    /// The constructs that `forbidden_construct` names (`ForbiddenConstructKind`).
    ConstructKind {
        Getattr,
        Hasattr,
        Cast,
        Eval,
        Exec,
        DynamicImport,
        TypeIgnore,
        AnyAnnotation,
        PlaceholderBody,
        Assert,
        BroadExcept,
        Setattr,
        Delattr,
        Vars,
        DunderDict,
        StringLiteralCompare,
    }
);

record!(
    pub(crate),
    /// One allowed suppression: its scope, line, statement and exact tag.
    TypeIgnore {
        qualified_name: Selector,
        line: u64,
        statement: String,
        tag: String,
    }
);

closed_enum!(SelectorRole {
    Read,
    Write,
    Call,
    Reflect,
    Constructor,
    TypeProbe,
    Equality,
    Membership,
    Match,
    Startswith,
    Endswith,
});

record!(
    pub(crate),
    /// One nominal receiver and member, with an optional literal operand.
    ConstructSelector {
        receiver: Selector,
        #[serde(skip_serializing_if = "Option::is_none")]
        member: Option<String>,
        role: SelectorRole,
        #[serde(skip_serializing_if = "Option::is_none")]
        literal: Option<String>,
    }
);

record!(pub(crate), ForbiddenConstruct {
    head: RuleHead,
    source: Selector,
    constructs: Vec<ConstructKind>,
    allowed_sources: Vec<Selector>,
    exact_sources: Vec<Selector>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    allowed_type_ignores: Vec<TypeIgnore>,
    #[serde(skip_serializing_if = "Option::is_none")]
    selector: Option<ConstructSelector>,
});

record!(pub(crate), ExternalDependencyScope {
    head: RuleHead,
    dependency: Selector,
    allowed_sources: Vec<Selector>,
    exact_sources: Vec<Selector>,
});

record!(
    pub(crate),
    /// `complete_assignment` and `complete_external_scope`: a rule over one source prefix.
    SourceRule {
        head: RuleHead,
        source: Selector,
    }
);

record!(pub(crate), RootLayout {
    head: RuleHead,
    root: Selector,
    allowed_children: Vec<Selector>,
});

record!(
    pub(crate),
    CompleteRequires {
        head: RuleHead,
        include_type_checking: bool,
    }
);

record!(pub(crate), LayerOrder {
    head: RuleHead,
    layers: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    components: Option<Vec<ComponentLabel>>,
});

closed_enum!(CycleLevel { Component, Module });

record!(pub(crate), NoComponentCycles {
    head: RuleHead,
    #[serde(skip_serializing_if = "is_component")]
    level: CycleLevel,
    #[serde(skip_serializing_if = "Option::is_none")]
    components: Option<Vec<ComponentLabel>>,
});

record!(
    pub(crate),
    /// One exact caller module can import one exact module object.
    ModuleObjectGrant {
        source_module: Selector,
        target_module: Selector,
    }
);

record!(pub(crate), InterfaceBoundary {
    head: RuleHead,
    include_type_checking: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    module_object_grants: Option<Vec<ModuleObjectGrant>>,
});

record!(pub(crate), SiblingIsolation {
    head: RuleHead,
    members: Vec<Selector>,
    include_type_checking: bool,
});

/// The defaults that the canonical bytes leave out: an absent permission keeps the amendment
/// digests of older contracts.
fn is_prefix(value: &SelectorMatch) -> bool {
    *value == SelectorMatch::Prefix
}

fn is_module(value: &TargetKind) -> bool {
    *value == TargetKind::Module
}

fn is_component(value: &CycleLevel) -> bool {
    *value == CycleLevel::Component
}
