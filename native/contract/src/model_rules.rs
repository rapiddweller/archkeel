// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The ten rule kinds that only the Python profile decides (`ir/model.py`).

use crate::model::{RuleHead, Selector, SelectorMatch};

closed_enum!(SymbolClassKind {
    Protocol,
    Enum,
    PydanticModel,
    Dataclass,
    Class,
});

record!(pub(crate), SymbolPlacement {
    head: RuleHead,
    source: Selector,
    class_kinds: Vec<SymbolClassKind>,
    allowed_sources: Vec<Selector>,
    exact_sources: Vec<Selector>,
});

closed_enum!(OwnershipMode { Retired, Confined });

closed_enum!(OwnershipRole {
    Definition,
    Read,
    Write,
    Delete,
    ValueTransfer,
    ParameterDefault,
    Fallback,
});

record!(pub(crate), SourceOwnership {
    head: RuleHead,
    source: Selector,
    mode: OwnershipMode,
    roles: Vec<OwnershipRole>,
    symbols: Vec<Selector>,
    parameters: Vec<Selector>,
    #[serde(skip_serializing_if = "Option::is_none")]
    owner: Option<Selector>,
    #[serde(skip_serializing_if = "Option::is_none")]
    value_owner: Option<Selector>,
});

record!(
    pub(crate),
    /// The origin and the shape of an alias body.
    AliasBody {
        origin: String,
        shape: String,
    }
);

record!(
    pub(crate),
    /// One allowed boundary type position (`BoundaryTypeAllowance`).
    BoundaryAllowance {
        qualified_name: String,
        position: String,
        field_path: String,
        annotation: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        container_depth: Option<u64>,
        #[serde(skip_serializing_if = "Option::is_none")]
        mapping_depth: Option<u64>,
        #[serde(skip_serializing_if = "Option::is_none")]
        alias_body: Option<AliasBody>,
        #[serde(skip_serializing_if = "Option::is_none")]
        key_alias_body: Option<AliasBody>,
        #[serde(skip_serializing_if = "Option::is_none")]
        literal_mapping_arm: Option<String>,
        #[serde(skip_serializing_if = "is_false")]
        native_mapping: bool,
    }
);

record!(pub(crate), BoundaryTypes {
    head: RuleHead,
    source: Selector,
    allowed_sources: Vec<Selector>,
    exact_sources: Vec<Selector>,
    allowed_positions: Vec<BoundaryAllowance>,
});

closed_enum!(ProtocolRole { Parameter, Member });

closed_enum!(ProtocolVisibility { Public, All });

record!(pub(crate), ProtocolSelector {
    role: ProtocolRole,
    name: String,
    visibility: ProtocolVisibility,
    optional: bool,
});

record!(pub(crate), ProtocolDeclarations {
    head: RuleHead,
    source: Selector,
    protocol: Selector,
    selectors: Vec<ProtocolSelector>,
});

record!(pub(crate), CallOwner {
    head: RuleHead,
    source: Selector,
    target: Selector,
    allowed_sources: Vec<Selector>,
    exact_sources: Vec<Selector>,
});

closed_enum!(NumericForm {
    Binary,
    Augmented,
    Both,
});

record!(pub(crate), BoundedNumericOperand {
    head: RuleHead,
    source: Selector,
    form: NumericForm,
    terminal_suffix: String,
    minimum_value: u64,
});

record!(pub(crate), ForbiddenCallArgument {
    head: RuleHead,
    source: Selector,
    target: Selector,
    parameter: String,
});

record!(pub(crate), CatalogArgument {
    head: RuleHead,
    source: Selector,
    target: Selector,
    parameter: String,
    catalog: Selector,
    overlays: Vec<String>,
    source_match: SelectorMatch,
});

record!(pub(crate), CatalogUse {
    head: RuleHead,
    source: Selector,
    catalog: Selector,
    overlays: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    member: Option<String>,
    source_match: SelectorMatch,
    #[serde(skip_serializing_if = "Option::is_none")]
    target: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    parameter: Option<String>,
});

closed_enum!(ConditionKind { Parameter, Member });

record!(pub(crate), Condition {
    kind: ConditionKind,
    owner: String,
    name: String,
});

record!(pub(crate), ForbiddenEffectUnderCondition {
    head: RuleHead,
    source: Selector,
    target: Selector,
    condition: Condition,
});

/// `native_mapping` is written only when it is true.
fn is_false(value: &bool) -> bool {
    !*value
}
