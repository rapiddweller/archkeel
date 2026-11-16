// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed rows of a section: the envelope that each row has, and one closed variant for each
//! row kind (AD-600).
//!
//! The builders in `sections.rs`, `topology.rs` and the report crate write the rows as JSON. The
//! frame holds them as `SectionRow`, so a row of an unknown kind, a row without a field and a row
//! with a foreign field never reach a frame, and the generated schema of the frame names each
//! field of each kind.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Whether the row states a fact of the code or a violation of a rule.
#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "UPPERCASE")]
enum EvidenceClass {
    Fact,
    Violation,
}

/// The area of the picture that a row belongs to.
#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum Area {
    PackageTopology,
    ModuleTopology,
    Cycles,
    Components,
    DependencyViolations,
    ApiSurface,
    Source,
    TypeArchitecture,
}

/// One row of a section: the envelope and the typed body (`kind` and `data`).
#[derive(Serialize, Deserialize, JsonSchema)]
pub(crate) struct SectionRow {
    id: String,
    evidence_class: EvidenceClass,
    area: Area,
    title: String,
    subjects: Vec<String>,
    evidence_ids: Vec<String>,
    rule_ids: Vec<String>,
    fact_ids: Vec<String>,
    provenance: Vec<String>,
    #[serde(flatten)]
    body: Body,
}

/// The kind of a row and the data that only this kind has.
#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", content = "data", rename_all = "snake_case")]
enum Body {
    PackageDependency(EdgeData),
    ModuleDependency(EdgeData),
    Module(ModuleData),
    Package(PackageData),
    PackageScc(SccData),
    ModuleScc(SccData),
    CompleteAssignment(CompleteAssignment),
    RootLayout(RootLayout),
    ExternalDependencyScope(ExternalDependencyScope),
    CompleteExternalScope(CompleteExternalScope),
    SiblingIsolation(SiblingIsolation),
    CompleteRequires(CompleteRequires),
    ForbiddenDependency(ForbiddenDependency),
    InterfaceBoundary(InterfaceBoundary),
    LayerOrder(LayerOrder),
    NoComponentCycles(ComponentCycle),
    ModuleCycle(ModuleCycle),
    BoundaryTypes(BoundaryTypes),
    ForbiddenConstruct(ConstructData),
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct EdgeData {
    level: String,
    source: String,
    target: String,
    count: usize,
    type_checking_count: usize,
    runtime_count: usize,
    source_rank: usize,
    target_rank: usize,
    bidirectional: bool,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ModuleData {
    qualified_name: String,
    package: String,
    file: String,
    symbol_count: Option<usize>,
    fan_in: usize,
    fan_out: usize,
    rank: usize,
    all_exports: Vec<String>,
    all_literal: bool,
    compatibility_logic_free: bool,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct PackageData {
    qualified_name: String,
    module_count: usize,
    fan_in: usize,
    fan_out: usize,
    rank: usize,
    dependencies: Vec<String>,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SccData {
    level: String,
    members: Vec<String>,
    internal_edges: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    backed_by: Option<Vec<String>>,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct CompleteAssignment {
    source: String,
    module: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct RootLayout {
    root: String,
    child: String,
    allowed_children: Vec<String>,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ExternalDependencyScope {
    source_module: String,
    target_module: String,
    dependency: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct CompleteExternalScope {
    source: String,
    source_module: String,
    target_module: String,
    dependency: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SiblingIsolation {
    source_module: String,
    target_module: String,
    source: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct CompleteRequires {
    source_module: String,
    target_module: String,
    source_component: String,
    target_component: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ForbiddenDependency {
    symbol: Option<String>,
    under_type_checking: bool,
    source_module: String,
    target_module: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct InterfaceBoundary {
    symbol: Option<String>,
    source_component: String,
    target_component: String,
    source_module: String,
    target_module: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct LayerOrder {
    source_component: String,
    target_component: String,
    source_layer: String,
    target_layer: String,
    rationale: String,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ComponentCycle {
    members: Vec<String>,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ModuleCycle {
    members: Vec<String>,
    edges: Vec<[String; 2]>,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct BoundaryTypes {
    qualified_name: String,
    position: String,
    annotation: String,
    reasons: Vec<String>,
}

/// A forbidden construct: with the selector of the rule, or the plain construct name.
#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(untagged)]
enum ConstructData {
    Selected(SelectedConstruct),
    Plain(PlainConstruct),
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SelectedConstruct {
    source: String,
    selector_role: String,
    receiver: String,
    member: Option<String>,
    literal: Option<String>,
}

#[derive(Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct PlainConstruct {
    source: String,
    construct: String,
}
