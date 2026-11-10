// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the calls, references and bindings sections.

use crate::ids::{EvidenceId, FactId, ModuleName};
use crate::nested::{CallArgument, CallBinding, Construction, GuardedEffect, ResultBinding};
use crate::nullable::{Literal, Nullable};
use crate::vocab::{ExpressionKind, ReferenceContext, Role, Status, TransferKind, Use};

facts_data! {
    /// A call site and the targets that it resolves to.
    pub struct CallData {
        [read skip] #[serde(default, skip_serializing_if = "Nullable::is_absent")] call_arguments: Nullable<Vec<CallArgument>>,
        [read skip] #[serde(default, skip_serializing_if = "Nullable::is_absent")] call_binding: Nullable<CallBinding>,
        [read] candidate_count: i64,
        [read] candidates_truncated: bool,
        [read skip] #[serde(default, skip_serializing_if = "Nullable::is_absent")] construction: Nullable<Construction>,
        [read] expression: String,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] guarded_effect: Option<Vec<GuardedEffect>>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] reason: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] result_bindings: Option<Vec<ResultBinding>>,
        [read skip] #[serde(default, skip_serializing_if = "Nullable::is_absent")] source_definition_id: Nullable<FactId>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] source_file: Option<String>,
        [read] source_module: ModuleName,
        [read] source_scope: String,
        [read] status: Status,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] target_evidence_ids: Option<Vec<EvidenceId>>,
        [read] targets: Vec<String>,
    }
}

facts_data! {
    /// A reference to a name and the targets that it resolves to.
    pub struct ReferenceData {
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] candidate_count: Option<i64>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] candidates_truncated: Option<bool>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_definition_id: Option<FactId>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_evidence_ids: Option<Vec<EvidenceId>>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_id: Option<FactId>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_owner_id: Option<FactId>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_owner_scope: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_role: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_scope: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] declaration_status: Option<String>,
        [read] expression: String,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] local_source_binding: Option<bool>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] reason: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] reference_context: Option<ReferenceContext>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] result_bindings: Option<Vec<ResultBinding>>,
        [read skip] #[serde(default, skip_serializing_if = "Nullable::is_absent")] source_definition_id: Nullable<FactId>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] source_file: Option<String>,
        [read] source_module: ModuleName,
        [read] source_scope: String,
        [read] status: Status,
        [read] targets: Vec<String>,
        [read "use"] #[serde(rename = "use")] use_: Use,
    }
}

facts_data! {
    /// The role of a source binding at one location (Python).
    pub struct SourceRoleData {
        [read] canonical_name: String,
        [wire] column: i64,
        [wire skip] #[serde(default, skip_serializing_if = "Nullable::is_absent")] constant: Nullable<Literal>,
        [wire] declaration_id: FactId,
        [wire] declaration_owner_id: FactId,
        [wire] declaration_owner_scope: String,
        [wire] end_column: i64,
        [wire] end_line: i64,
        [wire] expression: String,
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] expression_kind: Option<ExpressionKind>,
        [wire] line: i64,
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] parameter: Option<String>,
        [read] role: Role,
        [read] source_module: ModuleName,
        [read] source_scope: String,
        [wire] status: Status,
        [read] targets: Vec<String>,
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] transfer_kind: Option<TransferKind>,
        [wire "use"] #[serde(rename = "use")] use_: Use,
    }
}

facts_data! {
    /// A binding that a module exports (TypeScript).
    pub struct BindingData {
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] binding: Option<String>,
        [wire] module: ModuleName,
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] name: Option<String>,
        [wire] source_module: ModuleName,
        [wire] source_scope: String,
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
