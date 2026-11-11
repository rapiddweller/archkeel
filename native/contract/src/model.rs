// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed and closed contract. Each type holds what the Python dataclass of the same name in
//! `ir/model.py` holds, so the canonical bytes come from the same values.

use serde::{Deserialize, Serialize};

use crate::version::ContractVersion;

/// The id of a contract item: a component or a rule.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ItemId(pub String);

/// The label of a component. A `requires` entry and a rule name a component by its label.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ComponentLabel(pub String);

/// The SHA-256 of the contract bytes in lower-case hex: the contract identity of a run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ContractDigest(pub String);

/// One parsed contract.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Contract {
    pub version: ContractVersion,
    pub schema: Option<String>,
    pub components: Vec<Component>,
    pub rules: Vec<Rule>,
    pub digest: ContractDigest,
}

/// Who decided a component, an edge or a rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecidedBy {
    Architect,
    Agent,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ComponentRole {
    Component,
    Interface,
    Contract,
    Projection,
    Foundation,
}

/// A planned component owns no module yet.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Lifecycle {
    Planned,
}

/// One component that its owner can import, and the reason (AD-32).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Requirement {
    pub component: ComponentLabel,
    pub rationale: String,
    pub through: Vec<String>,
    pub decided_by: Option<DecidedBy>,
}

/// One component. An absent optional field stays absent in the canonical bytes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Component {
    pub id: ItemId,
    pub label: ComponentLabel,
    pub role: ComponentRole,
    pub packages: Vec<String>,
    pub responsibilities: Vec<String>,
    pub forbidden_responsibilities: Vec<String>,
    pub provenance: Vec<String>,
    pub capability_id: Option<ItemId>,
    pub requires: Option<Vec<Requirement>>,
    pub inside: Option<String>,
    pub public: Option<Vec<String>>,
    pub planned: Option<Vec<String>>,
    pub decided_by: Option<DecidedBy>,
    pub namespace: Option<String>,
    /// Empty when the contract declares no exact module.
    pub exact_modules: Vec<String>,
    pub layer: Option<String>,
    pub lifecycle: Option<Lifecycle>,
}

/// The 22 rule kinds of the grammar (`ArchitectureRuleKind`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuleKind {
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

/// The fields that each rule holds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuleHead {
    pub id: ItemId,
    pub rationale: String,
    pub provenance: Vec<String>,
    pub decided_by: DecidedBy,
}

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

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SelectorMatch {
    Prefix,
    Exact,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TargetKind {
    Module,
    ImportNamespace,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ForbiddenDependency {
    pub head: RuleHead,
    pub source: String,
    pub target: String,
    pub include_type_checking: bool,
    pub target_symbol: Option<String>,
    pub allowed_sources: Vec<String>,
    pub source_match: SelectorMatch,
    pub target_match: SelectorMatch,
    pub target_kind: TargetKind,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AllowedDependency {
    pub head: RuleHead,
    pub source: String,
    pub target: String,
}

/// The constructs that `forbidden_construct` names (`ForbiddenConstructKind`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConstructKind {
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

/// One allowed suppression: its scope, line, statement and exact tag.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TypeIgnore {
    pub qualified_name: String,
    pub line: u64,
    pub statement: String,
    pub tag: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SelectorRole {
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
}

/// One nominal receiver and member, with an optional literal operand.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConstructSelector {
    pub receiver: String,
    pub member: Option<String>,
    pub role: SelectorRole,
    pub literal: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ForbiddenConstruct {
    pub head: RuleHead,
    pub source: String,
    pub constructs: Vec<ConstructKind>,
    pub allowed_sources: Vec<String>,
    pub exact_sources: Vec<String>,
    pub allowed_type_ignores: Vec<TypeIgnore>,
    pub selector: Option<ConstructSelector>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExternalDependencyScope {
    pub head: RuleHead,
    pub dependency: String,
    pub allowed_sources: Vec<String>,
    pub exact_sources: Vec<String>,
}

/// `complete_assignment` and `complete_external_scope`: a rule over one source prefix.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceRule {
    pub head: RuleHead,
    pub source: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RootLayout {
    pub head: RuleHead,
    pub root: String,
    pub allowed_children: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CompleteRequires {
    pub head: RuleHead,
    pub include_type_checking: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LayerOrder {
    pub head: RuleHead,
    pub layers: Vec<String>,
    pub components: Option<Vec<ComponentLabel>>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CycleLevel {
    Component,
    Module,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NoComponentCycles {
    pub head: RuleHead,
    pub level: CycleLevel,
    pub components: Option<Vec<ComponentLabel>>,
}

/// One exact caller module can import one exact module object.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModuleObjectGrant {
    pub source_module: String,
    pub target_module: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InterfaceBoundary {
    pub head: RuleHead,
    pub include_type_checking: bool,
    pub module_object_grants: Option<Vec<ModuleObjectGrant>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SiblingIsolation {
    pub head: RuleHead,
    pub members: Vec<String>,
    pub include_type_checking: bool,
}
