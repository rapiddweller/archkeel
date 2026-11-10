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
        [read skip] call_arguments: Nullable<Vec<CallArgument>>,
        [read skip] call_binding: Nullable<CallBinding>,
        [read] candidate_count: i64,
        [read] candidates_truncated: bool,
        [read skip] construction: Nullable<Construction>,
        [read] expression: String,
        [read skip] guarded_effect: Option<Vec<GuardedEffect>>,
        [read skip] reason: Option<String>,
        [read skip] result_bindings: Option<Vec<ResultBinding>>,
        [read skip] source_definition_id: Nullable<FactId>,
        [read skip] source_file: Option<String>,
        [read] source_module: ModuleName,
        [read] source_scope: String,
        [read] status: Status,
        [read skip] target_evidence_ids: Option<Vec<EvidenceId>>,
        [read] targets: Vec<String>,
    }
}

facts_data! {
    /// A reference to a name and the targets that it resolves to.
    pub struct ReferenceData {
        [read skip] candidate_count: Option<i64>,
        [read skip] candidates_truncated: Option<bool>,
        [read skip] declaration_definition_id: Option<FactId>,
        [read skip] declaration_evidence_ids: Option<Vec<EvidenceId>>,
        [read skip] declaration_id: Option<FactId>,
        [read skip] declaration_owner_id: Option<FactId>,
        [read skip] declaration_owner_scope: Option<String>,
        [read skip] declaration_role: Option<String>,
        [read skip] declaration_scope: Option<String>,
        [read skip] declaration_status: Option<String>,
        [read] expression: String,
        [read skip] local_source_binding: Option<bool>,
        [read skip] reason: Option<String>,
        [read skip] reference_context: Option<ReferenceContext>,
        [read skip] result_bindings: Option<Vec<ResultBinding>>,
        [read skip] source_definition_id: Nullable<FactId>,
        [read skip] source_file: Option<String>,
        [read] source_module: ModuleName,
        [read] source_scope: String,
        [read] status: Status,
        [read] targets: Vec<String>,
        [read "use"] use_: Use,
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

facts_data! {
    /// A binding that a module exports (TypeScript).
    pub struct BindingData {
        [wire skip] binding: Option<String>,
        [wire] module: ModuleName,
        [wire skip] name: Option<String>,
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
