// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The ten rule kinds that only the Python profile decides (`ir/model.py`).

use crate::model::{is_false, RuleHead, Selector, SelectorMatch};

closed_enum!(
    /// The kind of a class that a placement rule judges.
    SymbolClassKind {
        /// A protocol.
        Protocol,
        /// An enum.
        Enum,
        /// A pydantic model.
        PydanticModel,
        /// A dataclass.
        Dataclass,
        /// A plain class.
        Class,
    }
);

record!(
    pub(crate),
    /// A rule on where a kind of class may live.
    SymbolPlacement {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The class kinds that the rule judges.
        class_kinds: Vec<SymbolClassKind>,
        /// The sources that the rule excepts by prefix.
        allowed_sources: Vec<Selector>,
        /// The sources that the rule excepts by exact name.
        exact_sources: Vec<Selector>,
    }
);

closed_enum!(
    /// How a rule limits the owner of a value.
    OwnershipMode {
        /// No owner may use the value.
        Retired,
        /// Only the owner may use the value.
        Confined,
    }
);

closed_enum!(
    /// The role that a value plays at a site.
    OwnershipRole {
        /// The site defines the value.
        Definition,
        /// The site reads the value.
        Read,
        /// The site writes the value.
        Write,
        /// The site deletes the value.
        Delete,
        /// The site passes the value on.
        ValueTransfer,
        /// The site is the default of a parameter.
        ParameterDefault,
        /// The site is a fallback.
        Fallback,
    }
);

record!(
    pub(crate),
    /// A rule on who owns a source value.
    SourceOwnership {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// How the rule limits the owner.
        mode: OwnershipMode,
        /// The roles that the rule judges.
        roles: Vec<OwnershipRole>,
        /// The symbols that the rule names.
        symbols: Vec<Selector>,
        /// The parameters that the rule names.
        parameters: Vec<Selector>,
        /// The owner of the value.
        #[serde(skip_serializing_if = "Option::is_none")]
        owner: Option<Selector>,
        /// The owner of the value that the symbol holds.
        #[serde(skip_serializing_if = "Option::is_none")]
        value_owner: Option<Selector>,
    }
);

record!(
    pub(crate),
    /// The origin and the shape of an alias body.
    AliasBody {
        /// Where the alias comes from.
        origin: String,
        /// The shape of the alias body.
        shape: String,
    }
);

record!(
    pub(crate),
    /// One allowed boundary type position (`BoundaryTypeAllowance`).
    BoundaryAllowance {
        /// The qualified name of the symbol.
        qualified_name: String,
        /// The parameter name or `return`.
        position: String,
        /// The path to the field.
        field_path: String,
        /// The annotation as written.
        annotation: String,
        /// How many containers wrap the type.
        #[serde(skip_serializing_if = "Option::is_none")]
        container_depth: Option<u64>,
        /// How many mappings wrap the type.
        #[serde(skip_serializing_if = "Option::is_none")]
        mapping_depth: Option<u64>,
        /// The body of the alias.
        #[serde(skip_serializing_if = "Option::is_none")]
        alias_body: Option<AliasBody>,
        /// The body of the alias of the mapping key.
        #[serde(skip_serializing_if = "Option::is_none")]
        key_alias_body: Option<AliasBody>,
        /// The arm of a literal mapping.
        #[serde(skip_serializing_if = "Option::is_none")]
        literal_mapping_arm: Option<String>,
        /// True when the mapping is a type of the language.
        #[serde(skip_serializing_if = "is_false")]
        native_mapping: bool,
    }
);

record!(
    pub(crate),
    /// A rule on the types at a boundary.
    BoundaryTypes {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The sources that the rule excepts by prefix.
        allowed_sources: Vec<Selector>,
        /// The sources that the rule excepts by exact name.
        exact_sources: Vec<Selector>,
        /// The positions that the rule accepts.
        allowed_positions: Vec<BoundaryAllowance>,
    }
);

closed_enum!(
    /// The role of a protocol member.
    ProtocolRole {
        /// The role is a parameter.
        Parameter,
        /// The role is a member.
        Member,
    }
);

closed_enum!(
    /// The visibility of a protocol member.
    ProtocolVisibility {
        /// Only the public members.
        Public,
        /// All members.
        All,
    }
);

record!(
    pub(crate),
    /// The selector of a protocol member.
    ProtocolSelector {
        /// The role that the rule reads.
        role: ProtocolRole,
        /// The name as written.
        name: String,
        /// The visibility of the member.
        visibility: ProtocolVisibility,
        /// True when the member is optional.
        optional: bool,
    }
);

record!(
    pub(crate),
    /// A rule on the declarations of a protocol.
    ProtocolDeclarations {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The protocol that the rule names.
        protocol: Selector,
        /// The selectors of the protocol members.
        selectors: Vec<ProtocolSelector>,
    }
);

record!(
    pub(crate),
    /// A rule on who may call a target.
    CallOwner {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The selector of the modules that the rule names as the other side.
        target: Selector,
        /// The sources that the rule excepts by prefix.
        allowed_sources: Vec<Selector>,
        /// The sources that the rule excepts by exact name.
        exact_sources: Vec<Selector>,
    }
);

closed_enum!(
    /// The written form of a numeric operand.
    NumericForm {
        /// A binary operation.
        Binary,
        /// An augmented assignment.
        Augmented,
        /// Either form.
        Both,
    }
);

record!(
    pub(crate),
    /// A rule on a bounded numeric operand.
    BoundedNumericOperand {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The written form that the rule reads.
        form: NumericForm,
        /// The suffix that ends the operand.
        terminal_suffix: String,
        /// The least value that the operand may have.
        minimum_value: u64,
    }
);

record!(
    pub(crate),
    /// A rule on an argument that no call may pass.
    ForbiddenCallArgument {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The selector of the modules that the rule names as the other side.
        target: Selector,
        /// The name of the parameter that the rule reads.
        parameter: String,
    }
);

record!(
    pub(crate),
    /// A rule on an argument that a catalog limits.
    CatalogArgument {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The selector of the modules that the rule names as the other side.
        target: Selector,
        /// The name of the parameter that the rule reads.
        parameter: String,
        /// The catalog of values that the rule checks against.
        catalog: Selector,
        /// The extra values that the contract adds to the catalog.
        overlays: Vec<String>,
        /// Whether the source selector matches by prefix or by exact name.
        source_match: SelectorMatch,
    }
);

record!(
    pub(crate),
    /// A rule on the use of a catalog value.
    CatalogUse {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The catalog of values that the rule checks against.
        catalog: Selector,
        /// The extra values that the contract adds to the catalog.
        overlays: Vec<String>,
        /// The member that the rule reads.
        #[serde(skip_serializing_if = "Option::is_none")]
        member: Option<String>,
        /// Whether the source selector matches by prefix or by exact name.
        source_match: SelectorMatch,
        /// The selector of the modules that the rule names as the other side.
        #[serde(skip_serializing_if = "Option::is_none")]
        target: Option<String>,
        /// The name of the parameter that the rule reads.
        #[serde(skip_serializing_if = "Option::is_none")]
        parameter: Option<String>,
    }
);

closed_enum!(
    /// The kind of a condition.
    ConditionKind {
        /// The condition reads a parameter.
        Parameter,
        /// The condition reads a member.
        Member,
    }
);

record!(
    pub(crate),
    /// The condition of an effect.
    Condition {
        /// The kind of the value.
        kind: ConditionKind,
        /// The component or symbol that owns the value.
        owner: String,
        /// The name as written.
        name: String,
    }
);

record!(
    pub(crate),
    /// A rule on an effect that a condition forbids.
    ForbiddenEffectUnderCondition {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules that the rule judges.
        source: Selector,
        /// The selector of the modules that the rule names as the other side.
        target: Selector,
        /// The condition of the effect.
        condition: Condition,
    }
);
