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
        /// The arguments of the call.
        [read skip] call_arguments: Nullable<Vec<CallArgument>>,
        /// What the call binds to.
        [read skip] call_binding: Nullable<CallBinding>,
        /// How many targets the site can resolve to.
        [read] candidate_count: i64,
        /// True when the list of targets is cut.
        [read] candidates_truncated: bool,
        /// What a construction call builds.
        [read skip] construction: Nullable<Construction>,
        /// The expression as written.
        [read] expression: String,
        /// The effects that only run under a guard.
        [read skip] guarded_effect: Option<Vec<GuardedEffect>>,
        /// Why the collector does not prove it.
        [read skip] reason: Option<String>,
        /// The bindings of the result.
        [read skip] result_bindings: Option<Vec<ResultBinding>>,
        /// The id of the definition that holds the source.
        [read skip] source_definition_id: Nullable<FactId>,
        /// The file that holds the source.
        [read skip] source_file: Option<String>,
        /// The module that holds the source.
        [read] source_module: ModuleName,
        /// The scope that holds the source.
        [read] source_scope: String,
        /// The proof state of the record.
        [read] status: Status,
        /// The evidence of the targets.
        [read skip] target_evidence_ids: Option<Vec<EvidenceId>>,
        /// The qualified names that it resolves to.
        [read] targets: Vec<String>,
    }
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

facts_data! {
    /// A reference to a name and the targets that it resolves to.
    pub struct ReferenceData {
        /// How many targets the site can resolve to.
        [read skip] candidate_count: Option<i64>,
        /// True when the list of targets is cut.
        [read skip] candidates_truncated: Option<bool>,
        /// The id of the definition of the declaration.
        [read skip] declaration_definition_id: Option<FactId>,
        /// The evidence of the declaration.
        [read skip] declaration_evidence_ids: Option<Vec<EvidenceId>>,
        /// The id of the declaration.
        [read skip] declaration_id: Option<FactId>,
        /// The id of the owner of the declaration.
        [read skip] declaration_owner_id: Option<FactId>,
        /// The scope of the owner of the declaration.
        [read skip] declaration_owner_scope: Option<String>,
        /// The role of the declaration.
        [read skip] declaration_role: Option<String>,
        /// The scope of the declaration.
        [read skip] declaration_scope: Option<String>,
        /// The proof state of the declaration.
        [read skip] declaration_status: Option<String>,
        /// The expression as written.
        [read] expression: String,
        /// True when a local statement binds the source name.
        [read skip] local_source_binding: Option<bool>,
        /// Why the collector does not prove it.
        [read skip] reason: Option<String>,
        /// The context of the reference.
        [read skip] reference_context: Option<ReferenceContext>,
        /// The bindings of the result.
        [read skip] result_bindings: Option<Vec<ResultBinding>>,
        /// The id of the definition that holds the source.
        [read skip] source_definition_id: Nullable<FactId>,
        /// The file that holds the source.
        [read skip] source_file: Option<String>,
        /// The module that holds the source.
        [read] source_module: ModuleName,
        /// The scope that holds the source.
        [read] source_scope: String,
        /// The proof state of the record.
        [read] status: Status,
        /// The qualified names that it resolves to.
        [read] targets: Vec<String>,
        /// How the value is used.
        [read "use"] use_: Use,
    }
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
        /// The canonical name of the value.
        [read] canonical_name: String,
        /// The first column of the place.
        [wire] column: i64,
        /// The constant value of the source, when it is one.
        [wire skip] constant: Nullable<Literal>,
        /// The id of the declaration.
        [wire] declaration_id: FactId,
        /// The id of the owner of the declaration.
        [wire] declaration_owner_id: FactId,
        /// The scope of the owner of the declaration.
        [wire] declaration_owner_scope: String,
        /// The last column of the place.
        [wire] end_column: i64,
        /// The last line of the place.
        [wire] end_line: i64,
        /// The expression as written.
        [wire] expression: String,
        /// The kind of the expression.
        [wire skip] expression_kind: Option<ExpressionKind>,
        /// The first line of the place, counted from 1.
        [wire] line: i64,
        /// The parameter that the site names.
        [wire skip] parameter: Option<String>,
        /// The role that the source plays.
        [read] role: Role,
        /// The module that holds the source.
        [read] source_module: ModuleName,
        /// The scope that holds the source.
        [read] source_scope: String,
        /// The proof state of the record.
        [wire] status: Status,
        /// The qualified names that it resolves to.
        [read] targets: Vec<String>,
        /// How the value passes to the target.
        [wire skip] transfer_kind: Option<TransferKind>,
        /// How the value is used.
        [wire "use"] use_: Use,
    }
}

facts_data! {
    /// A binding that a module exports (TypeScript).
    pub struct BindingData {
        /// The name that the import binds.
        [wire skip] binding: Option<String>,
        /// The module that holds it.
        [wire] module: ModuleName,
        /// The bound name.
        [wire skip] name: Option<String>,
        /// The global that a script import binds.
        [wire skip] script_global: Option<String>,
        /// The namespace of a script binding.
        [wire skip] script_namespace: Option<String>,
        /// The module that holds the source.
        [wire] source_module: ModuleName,
        /// The scope that holds the source.
        [wire] source_scope: String,
    }
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
        /// The binding that nothing uses.
        [read] binding: String,
        /// The module that holds it.
        [read] module: ModuleName,
        /// The bound name.
        [read] name: String,
        /// The scope that holds the binding.
        [read] owner: String,
    }
}
