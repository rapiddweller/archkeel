// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed and closed contract. Each type holds what the Python dataclass of the same name in
//! `ir/model.py` holds, so the canonical bytes come from the same values.
//!
//! The fields are private to the crate and each has a read accessor. So a `Contract` and each value
//! in it come only from `parse`: a caller cannot build or change one.

use serde::{Deserialize, Serialize};

use crate::version::ContractVersion;

/// A text value that only this crate can make.
pub(crate) trait Wrap {
    fn wrap(text: String) -> Self;
}

/// The text of a text value, for the canonical writer.
pub(crate) trait TextOf {
    fn text_of(&self) -> &str;
}

impl Wrap for String {
    fn wrap(text: String) -> Self {
        text
    }
}

impl TextOf for str {
    fn text_of(&self) -> &str {
        self
    }
}

impl TextOf for String {
    fn text_of(&self) -> &str {
        self
    }
}

/// Wrap each text.
pub(crate) fn wrap_all<T: Wrap>(texts: Vec<String>) -> Vec<T> {
    texts.into_iter().map(T::wrap).collect()
}

/// Declare a text newtype with a read accessor and no public constructor. The call passes the
/// visibility of the inner text (the crate), so the definition names no `crate` that the scan
/// cannot place.
macro_rules! text_type {
    ($inner:vis, $(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
        pub struct $name($inner String);

        impl $name {
            /// The text of the value.
            pub fn as_text(&self) -> &str {
                &self.0
            }
        }

        impl Wrap for $name {
            fn wrap(text: String) -> $name {
                $name(text)
            }
        }

        impl TextOf for $name {
            fn text_of(&self) -> &str {
                &self.0
            }
        }
    };
}

/// Declare a struct with fields of the visibility that the call passes (the crate) and a public
/// read accessor for each field.
macro_rules! record {
    ($inner:vis, $(#[$meta:meta])* $name:ident { $($(#[$field_meta:meta])* $field:ident: $kind:ty),* $(,)? }) => {
        $(#[$meta])*
        #[derive(Clone, Debug, PartialEq, Eq)]
        pub struct $name {
            $($(#[$field_meta])* $inner $field: $kind),*
        }

        impl $name {
            $(
                $(#[$field_meta])*
                pub fn $field(&self) -> &$kind {
                    &self.$field
                }
            )*
        }
    };
}

/// Declare a closed enum whose words are the snake case names of its variants.
macro_rules! closed_enum {
    ($(#[$meta:meta])* $name:ident { $($variant:ident),* $(,)? }) => {
        $(#[$meta])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
        #[serde(rename_all = "snake_case")]
        pub enum $name {
            $($variant),*
        }
    };
}

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
    /// The SHA-256 of bytes in lower-case hex.
    ContractDigest
);

record!(
    pub(crate),
    /// One parsed contract. Its digest is the SHA-256 of the bytes: the contract identity of a run.
    Contract {
        version: ContractVersion,
        schema: Option<String>,
        components: Vec<Component>,
        rules: Vec<Rule>,
        digest: ContractDigest,
    }
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
        capability_id: Option<ItemId>,
        requires: Option<Vec<Requirement>>,
        inside: Option<String>,
        public: Option<Vec<Selector>>,
        planned: Option<Vec<Selector>>,
        decided_by: Option<DecidedBy>,
        namespace: Option<Package>,
        /// Empty when the contract declares no exact module.
        exact_modules: Vec<Package>,
        layer: Option<String>,
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

/// One rule of a structural kind. The other ten kinds are `Unsupported` until slice 0c-2.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Rule {
    ForbiddenDependency(ForbiddenDependency),
    AllowedDependency(AllowedDependency),
    ForbiddenConstruct(ForbiddenConstruct),
    ExternalDependencyScope(ExternalDependencyScope),
    CompleteAssignment(SourceRule),
    RootLayout(RootLayout),
    CompleteExternalScope(SourceRule),
    CompleteRequires(CompleteRequires),
    LayerOrder(LayerOrder),
    NoComponentCycles(NoComponentCycles),
    InterfaceBoundary(InterfaceBoundary),
    SiblingIsolation(SiblingIsolation),
}

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
    target_symbol: Option<String>,
    allowed_sources: Vec<Selector>,
    source_match: SelectorMatch,
    target_match: SelectorMatch,
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
        member: Option<String>,
        role: SelectorRole,
        literal: Option<String>,
    }
);

record!(pub(crate), ForbiddenConstruct {
    head: RuleHead,
    source: Selector,
    constructs: Vec<ConstructKind>,
    allowed_sources: Vec<Selector>,
    exact_sources: Vec<Selector>,
    allowed_type_ignores: Vec<TypeIgnore>,
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
    components: Option<Vec<ComponentLabel>>,
});

closed_enum!(CycleLevel { Component, Module });

record!(pub(crate), NoComponentCycles {
    head: RuleHead,
    level: CycleLevel,
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
    module_object_grants: Option<Vec<ModuleObjectGrant>>,
});

record!(pub(crate), SiblingIsolation {
    head: RuleHead,
    members: Vec<Selector>,
    include_type_checking: bool,
});
