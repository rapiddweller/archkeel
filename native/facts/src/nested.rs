// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The objects inside the data of a record. Each one is closed: an unknown key is an error.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::ids::{EvidenceId, FactId, ModuleName};
use crate::nullable::Nullable;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AttributeDeclaration {
    pub annotation: Option<String>,
    #[serde(default, skip_serializing_if = "Nullable::is_absent")]
    pub constant: Nullable<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decorator_evidence_ids: Option<Vec<EvidenceId>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decorators: Option<Vec<String>>,
    pub definition_id: FactId,
    pub evidence_ids: Vec<EvidenceId>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub literal_value: Option<String>,
    pub name: String,
    #[serde(rename = "static", default, skip_serializing_if = "Option::is_none")]
    pub is_static: Option<bool>,
    pub visibility: VisibilityDetail,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BaseDeclaration {
    pub candidate_count: i64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub candidates_truncated: Option<bool>,
    pub evidence_ids: Vec<EvidenceId>,
    pub expression: String,
    pub id: FactId,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    pub relationship_kind: String,
    pub status: String,
    pub targets: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BindingScope {
    pub scope_evidence_id: EvidenceId,
    pub scope_owner: String,
    pub scope_symbol_id: FactId,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallArgument {
    pub evidence_ids: Vec<EvidenceId>,
    pub keyword: Option<String>,
    pub kind: String,
    pub value: Option<String>,
    pub value_kind: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallBinding {
    pub evidence_ids: Vec<EvidenceId>,
    pub origin: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub proof: Option<CallBindingProof>,
    pub target: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Construction {
    pub candidates_truncated: bool,
    pub reason: String,
    pub status: String,
    pub targets: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ContextmanagerSignature {
    pub abc: ContextmanagerAbc,
    pub effective_return: EffectiveReturn,
    pub factory: String,
    pub kind: String,
    pub partial: ContextmanagerPartial,
    pub support_evidence_ids: Vec<EvidenceId>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DefinitionContext {
    pub branch: String,
    pub evidence_ids: Vec<EvidenceId>,
    pub kind: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Field {
    pub annotation: String,
    pub name: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GenericBase {
    pub arguments: Vec<String>,
    pub arguments_are_names: Vec<bool>,
    pub base: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GuardBooleanMember {
    pub evidence_ids: Vec<EvidenceId>,
    pub name: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GuardedEffect {
    pub complete: bool,
    pub condition: Condition,
    pub condition_evidence_ids: Vec<EvidenceId>,
    pub condition_value: Option<bool>,
    pub effect_binding_evidence_ids: Vec<EvidenceId>,
    pub helper_bindings: Vec<String>,
    pub path_evidence_ids: Vec<EvidenceId>,
    pub unknown_reason: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MemberInventory {
    pub definition_ids: Vec<FactId>,
    pub kind: String,
    pub reason: Option<String>,
    pub schema_version: String,
    pub status: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Parameter {
    pub annotation: Option<String>,
    pub default: Option<String>,
    pub default_known: bool,
    pub kind: String,
    pub name: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PropertyBinding {
    pub line: i64,
    pub operation: String,
    pub source: String,
    pub source_line: i64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReceiverBinding {
    pub evidence_ids: Vec<EvidenceId>,
    pub origin: String,
    pub target: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ResultBinding {
    pub annotation: Option<String>,
    pub definition_contexts: Vec<DefinitionContext>,
    pub evidence_ids: Vec<EvidenceId>,
    pub id: FactId,
    pub initializer: String,
    pub name: String,
    pub target_kind: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StoredFieldWrite {
    pub annotation_evidence_id: EvidenceId,
    pub evidence_id: EvidenceId,
    pub field: String,
    pub parameter: String,
    pub receiver: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VisibilityDetail {
    pub basis: String,
    pub kind: String,
    pub spelling: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallBindingProof {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub constructor_evidence_id: Option<EvidenceId>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_member: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_owner_module: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_owner_qualname: Option<String>,
    pub kind: String,
    #[serde(default, skip_serializing_if = "Nullable::is_absent")]
    pub provider_evidence_id: Nullable<EvidenceId>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_implementation: Option<String>,
    pub runtime_name: String,
    pub runtime_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stdlib_source_digest: Option<String>,
    pub target: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub witness_evidence_ids: Option<Vec<EvidenceId>>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Condition {
    pub kind: String,
    pub name: String,
    pub owner: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ContextmanagerAbc {
    pub kind: String,
    pub members: Vec<String>,
    pub module: ModuleName,
    pub origin: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ContextmanagerPartial {
    pub cache_tag: String,
    pub implementation: String,
    pub kind: String,
    pub origin: String,
    pub version: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct EffectiveReturn {
    pub payload: String,
    pub wrapper: String,
}
