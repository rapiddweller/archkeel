// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The objects inside the data of a record. Each one is closed: an unknown key is an error.

use std::collections::BTreeMap;

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::ids::{EvidenceId, FactId, ModuleName};
use crate::nullable::Nullable;
use crate::type_shape::TypeShape;
use crate::vocab::{InventoryStatus, MemberKind, RelationshipKind, Status};

/// One attribute of a class as the collector declares it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AttributeDeclaration {
    /// The annotation as written.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub annotation: Option<String>,
    /// The value of a constant attribute, when it is one.
    #[serde(default, skip_serializing_if = "Nullable::is_absent")]
    pub constant: Nullable<String>,
    /// The evidence of the decorators.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decorator_evidence_ids: Option<Vec<EvidenceId>>,
    /// The decorators as written.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decorators: Option<Vec<String>>,
    /// The id of the symbol that defines the attribute.
    pub definition_id: FactId,
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// The inferred builtin identity and the proven bindings of builtin names in this scope.
    /// Only the linked collector states this proof.
    #[serde(skip)]
    pub inferred_builtin_type: Option<(String, BTreeMap<String, String>)>,
    /// The literal value of the attribute, as written.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub literal_value: Option<String>,
    /// The name as written.
    pub name: String,
    /// True when the attribute belongs to the class and not to an instance.
    #[serde(rename = "static", default, skip_serializing_if = "Option::is_none")]
    pub is_static: Option<bool>,
    /// How the visibility is written and why it holds.
    pub visibility: VisibilityDetail,
}

/// One base that a class names, with the targets that it resolves to.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BaseDeclaration {
    /// How many targets the base can resolve to.
    pub candidate_count: i64,
    /// True when the list of targets is cut.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub candidates_truncated: Option<bool>,
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// The base as written.
    pub expression: String,
    /// The id of the record.
    pub id: FactId,
    /// Why the collector does not prove it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    /// The kind of the relationship with the base.
    pub relationship_kind: RelationshipKind,
    /// The proof state of the value.
    pub status: Status,
    /// The qualified names that the value can resolve to.
    pub targets: Vec<String>,
}

/// The scope that a binding is made in.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BindingScope {
    /// The evidence of the scope.
    pub scope_evidence_id: EvidenceId,
    /// The qualified name of the owner of the scope.
    pub scope_owner: String,
    /// The id of the symbol of the scope.
    pub scope_symbol_id: FactId,
}

/// One argument of a call.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallArgument {
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// The keyword of the argument, when it has one.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub keyword: Option<String>,
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The argument as written.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub value: Option<String>,
    /// The kind of the value of the argument.
    pub value_kind: String,
}

/// What a call binds to, with its origin and proof.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallBinding {
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// Where the value comes from.
    pub origin: String,
    /// The proof of the binding.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub proof: Option<CallBindingProof>,
    /// The qualified name that it resolves to.
    pub target: String,
}

/// What a construction expression builds: the status and the candidate targets.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Construction {
    /// True when the list of targets is cut.
    pub candidates_truncated: bool,
    /// Why the collector does not prove it.
    pub reason: String,
    /// The proof state of the value.
    pub status: Status,
    /// The qualified names that the value can resolve to.
    pub targets: Vec<String>,
}

/// The signature facts of a context manager factory.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ContextmanagerSignature {
    /// The abstract base that proves the context manager.
    pub abc: ContextmanagerAbc,
    /// The type that the factory returns after its wrapper.
    pub effective_return: EffectiveReturn,
    /// The name of the factory.
    pub factory: String,
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The partial application that proves the context manager.
    pub partial: ContextmanagerPartial,
    /// The evidence of the signature.
    pub support_evidence_ids: Vec<EvidenceId>,
}

/// The place where a definition is made, such as a branch of a condition.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DefinitionContext {
    /// The branch of the condition that holds the definition.
    pub branch: String,
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// The kind of the value, as a closed word.
    pub kind: String,
}

/// One field of a class: its name and written type.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Field {
    /// The type of the field as written.
    pub annotation: String,
    /// The name as written.
    pub name: String,
}

/// A generic base with the arguments that it is applied to.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GenericBase {
    /// The arguments of the generic as written.
    pub arguments: Vec<String>,
    /// For each argument, true when it is a plain name.
    pub arguments_are_names: Vec<bool>,
    /// The generic that the arguments apply to.
    pub base: String,
}

/// A boolean member that a guard reads.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GuardBooleanMember {
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// The name as written.
    pub name: String,
}

/// An effect that only runs under a guard, with the proof of the guard.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GuardedEffect {
    /// True when the collector reads the whole effect.
    pub complete: bool,
    /// The condition of the guard.
    pub condition: Condition,
    /// The evidence of the condition.
    pub condition_evidence_ids: Vec<EvidenceId>,
    /// The value of the condition, when the collector proves it.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub condition_value: Option<bool>,
    /// The evidence of the bindings that the effect makes.
    pub effect_binding_evidence_ids: Vec<EvidenceId>,
    /// The helpers that the effect binds.
    pub helper_bindings: Vec<String>,
    /// The evidence of the path to the effect.
    pub path_evidence_ids: Vec<EvidenceId>,
    /// Why the condition is not proven.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub unknown_reason: Option<String>,
}

/// The inventory of the members of one kind that a class has, and whether it is complete.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MemberInventory {
    /// The ids of the symbols that define the members.
    pub definition_ids: Vec<FactId>,
    /// The kind of the members.
    pub kind: MemberKind,
    /// Why the collector does not prove it.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub reason: Option<String>,
    /// The version of the inventory format.
    pub schema_version: String,
    /// Whether the inventory is complete.
    pub status: InventoryStatus,
}

/// One parameter of a function: its name, kind, annotation and default.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Parameter {
    /// The annotation as written.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub annotation: Option<String>,
    /// The default value as written.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub default: Option<String>,
    /// True when the collector reads the default.
    pub default_known: bool,
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The name as written.
    pub name: String,
    /// The written type as a tree (AD-550). Absent when the collector does not write shapes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub shape: Option<TypeShape>,
}

/// The binding that a property operation makes.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PropertyBinding {
    /// The line of the place, counted from 1.
    pub line: i64,
    /// The operation that the property performs.
    pub operation: String,
    /// The member that the property reads or writes.
    pub source: String,
    /// The line of that member.
    pub source_line: i64,
}

/// What the receiver of a call binds to.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReceiverBinding {
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// Where the value comes from.
    pub origin: String,
    /// The qualified name that it resolves to.
    pub target: String,
}

/// The binding of a result to a name, with its initializer.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ResultBinding {
    /// The annotation as written.
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub annotation: Option<String>,
    /// The static type spelling proven by the linked collector for an untyped local.
    #[serde(skip)]
    pub inferred_type: Option<String>,
    /// The places where the binding is defined.
    pub definition_contexts: Vec<DefinitionContext>,
    /// The ids of the evidence records that back the value.
    pub evidence_ids: Vec<EvidenceId>,
    /// The id of the record.
    pub id: FactId,
    /// The expression that sets the value.
    pub initializer: String,
    /// The name as written.
    pub name: String,
    /// The kind of the target of the binding.
    pub target_kind: String,
}

/// A write of a parameter into a field of the receiver.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StoredFieldWrite {
    /// The evidence of the annotation of the field.
    pub annotation_evidence_id: EvidenceId,
    /// The evidence of the write.
    pub evidence_id: EvidenceId,
    /// The field that is written.
    pub field: String,
    /// The parameter that is stored.
    pub parameter: String,
    /// The receiver that holds the field.
    pub receiver: String,
}

/// How the visibility of a name is written and why it holds.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VisibilityDetail {
    /// The rule that decides the visibility.
    pub basis: String,
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The name as written, which can decide the visibility.
    pub spelling: String,
}

/// The proof that supports a call binding.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallBindingProof {
    /// The evidence of the constructor.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub constructor_evidence_id: Option<EvidenceId>,
    /// The kind of the descriptor.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_kind: Option<String>,
    /// The member that the descriptor binds.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_member: Option<String>,
    /// The module of the owner of the descriptor.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_owner_module: Option<String>,
    /// The qualified name of the owner of the descriptor.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_owner_qualname: Option<String>,
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The evidence of the provider.
    #[serde(default, skip_serializing_if = "Nullable::is_absent")]
    pub provider_evidence_id: Nullable<EvidenceId>,
    /// The implementation of the runtime that proves the binding.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_implementation: Option<String>,
    /// The name of the runtime that proves the binding.
    pub runtime_name: String,
    /// The version of the runtime that proves the binding.
    pub runtime_version: String,
    /// The digest of the standard library source that proves the binding.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stdlib_source_digest: Option<String>,
    /// The qualified name that it resolves to.
    pub target: String,
    /// The evidence that witnesses the binding.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub witness_evidence_ids: Option<Vec<EvidenceId>>,
}

/// The condition of a guard.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Condition {
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The name as written.
    pub name: String,
    /// The symbol that the condition belongs to.
    pub owner: String,
}

/// The abstract base that proves a context manager.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ContextmanagerAbc {
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// The members of the abstract base.
    pub members: Vec<String>,
    /// The module of the abstract base.
    pub module: ModuleName,
    /// Where the value comes from.
    pub origin: String,
}

/// The partial application that proves a context manager.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ContextmanagerPartial {
    /// The cache tag of the runtime.
    pub cache_tag: String,
    /// The implementation of the runtime.
    pub implementation: String,
    /// The kind of the value, as a closed word.
    pub kind: String,
    /// Where the value comes from.
    pub origin: String,
    /// The version of the runtime.
    pub version: String,
}

/// The type that a context manager factory returns after its wrapper.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct EffectiveReturn {
    /// The type that the factory yields.
    pub payload: String,
    /// The wrapper type that the factory returns.
    pub wrapper: String,
}

/// One explicit actual: an optional keyword and whether the source writes a string literal.
pub type WrittenActual = (Option<String>, bool);
/// A live call site, its exact declaration, optional import and actuals when bindable.
pub type DirectCall = (FactId, FactId, Option<FactId>, Option<Vec<WrittenActual>>);

/// A written callee and its matching declaration. These locations provide source navigation only.
#[derive(Clone, Debug, PartialEq, Serialize, JsonSchema)]
pub struct SourceCallCandidate {
    /// Module containing the call.
    pub source_module: String,
    /// Module containing the declaration.
    pub target_module: String,
    /// Qualified declaration name.
    pub target: String,
    /// Written callee.
    pub expression: String,
    /// Location of the callee at this call site.
    pub call_evidence: EvidenceId,
    /// Location of the name in the class or function definition.
    pub declaration_evidence: EvidenceId,
}
