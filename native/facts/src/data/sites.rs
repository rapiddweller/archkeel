// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the calls, references and bindings sections.

use crate::ids::{EvidenceId, FactId, ModuleName};
use crate::nested::{CallArgument, CallBinding, Construction, GuardedEffect, ResultBinding};
use crate::nullable::{Literal, Nullable};
use crate::vocab::{ExpressionKind, ReferenceContext, Role, Status, TransferKind, Use};

/// A call site and the targets that it resolves to.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallData {
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub call_arguments: Nullable<Vec<CallArgument>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub call_binding: Nullable<CallBinding>,
    pub candidate_count: i64,
    pub candidates_truncated: bool,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub construction: Nullable<Construction>,
    pub expression: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub guarded_effect: Option<Vec<GuardedEffect>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub result_bindings: Option<Vec<ResultBinding>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_definition_id: Nullable<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_file: Option<String>,
    pub source_module: ModuleName,
    pub source_scope: String,
    pub status: Status,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub target_evidence_ids: Option<Vec<EvidenceId>>,
    pub targets: Vec<String>,
}

impl CallData {
    /// A call site of the source scope `scope` with the targets that it resolves to. The other
    /// fields are absent.
    pub fn new(
        expression: String,
        (source_module, source_scope): (ModuleName, String),
        status: Status,
        targets: Vec<String>,
    ) -> Self {
        Self {
            call_arguments: Nullable::Absent,
            call_binding: Nullable::Absent,
            candidate_count: i64::try_from(targets.len()).unwrap_or(i64::MAX),
            candidates_truncated: false,
            construction: Nullable::Absent,
            expression,
            guarded_effect: None,
            reason: None,
            result_bindings: None,
            source_definition_id: Nullable::Absent,
            source_file: None,
            source_module,
            source_scope,
            status,
            target_evidence_ids: None,
            targets,
        }
    }
}

/// A reference to a name and the targets that it resolves to.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReferenceData {
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub candidate_count: Option<i64>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub candidates_truncated: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_definition_id: Option<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_evidence_ids: Option<Vec<EvidenceId>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_id: Option<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_owner_id: Option<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_owner_scope: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_role: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_scope: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declaration_status: Option<String>,
    pub expression: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub local_source_binding: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub reference_context: Option<ReferenceContext>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub result_bindings: Option<Vec<ResultBinding>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_definition_id: Nullable<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_file: Option<String>,
    pub source_module: ModuleName,
    pub source_scope: String,
    pub status: Status,
    pub targets: Vec<String>,
    #[serde(rename = "use")]
    pub use_: Use,
}

impl ReferenceData {
    /// A reference in the source scope `scope` with the targets that it resolves to. The other
    /// fields are absent.
    pub fn new(
        expression: String,
        (source_module, source_scope): (ModuleName, String),
        (status, use_): (Status, Use),
        targets: Vec<String>,
    ) -> Self {
        Self {
            candidate_count: Some(i64::try_from(targets.len()).unwrap_or(i64::MAX)),
            candidates_truncated: Some(false),
            declaration_definition_id: None,
            declaration_evidence_ids: None,
            declaration_id: None,
            declaration_owner_id: None,
            declaration_owner_scope: None,
            declaration_role: None,
            declaration_scope: None,
            declaration_status: None,
            expression,
            local_source_binding: None,
            reason: None,
            reference_context: None,
            result_bindings: None,
            source_definition_id: Nullable::Absent,
            source_file: None,
            source_module,
            source_scope,
            status,
            targets,
            use_,
        }
    }
}

facts_data! {
    /// The role of a source binding at one location (Python).
    pub struct SourceRoleData {
        [read] canonical_name: String,
        [wire] column: i64,
        [wire skip] constant: Nullable<Literal>,
        [wire] declaration_id: FactId,
        [wire] declaration_owner_id: FactId,
        [wire] declaration_owner_scope: String,
        [wire] end_column: i64,
        [wire] end_line: i64,
        [wire] expression: String,
        [wire skip] expression_kind: Option<ExpressionKind>,
        [wire] line: i64,
        [wire skip] parameter: Option<String>,
        [read] role: Role,
        [read] source_module: ModuleName,
        [read] source_scope: String,
        [wire] status: Status,
        [read] targets: Vec<String>,
        [wire skip] transfer_kind: Option<TransferKind>,
        [wire "use"] use_: Use,
    }
}

/// A binding that a module exports (TypeScript).
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BindingData {
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub binding: Option<String>,
    pub module: ModuleName,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub script_global: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub script_namespace: Option<String>,
    pub source_module: ModuleName,
    pub source_scope: String,
}

impl BindingData {
    /// A binding record of the module `module`: the module three times, and no name.
    pub fn in_module(module: &str) -> Self {
        Self {
            binding: None,
            module: ModuleName::new(module),
            name: None,
            script_global: None,
            script_namespace: None,
            source_module: ModuleName::new(module),
            source_scope: module.to_owned(),
        }
    }

    /// A binding that proves an export has a `name` and no `binding`; a result binding is the
    /// other way round.
    pub fn exports_name(&self) -> bool {
        self.name.is_some()
    }
}

facts_data! {
    /// A parameter or a local name that is never read (Python).
    pub struct UnusedBindingData {
        [read] binding: String,
        [read] module: ModuleName,
        [read] name: String,
        [read] owner: String,
    }
}
