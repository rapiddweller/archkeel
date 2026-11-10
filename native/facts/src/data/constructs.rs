// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the constructs and typing_signals sections.

use crate::ids::ModuleName;
use crate::nested::{BindingScope, ReceiverBinding};
use crate::vocab::{Operation, Proof, SelectorRole, Status};

facts_data! {
    /// A written construct that a rule can forbid.
    pub struct ConstructData {
        [read] construct: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] form: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] handled: Option<Vec<String>>,
        [read] owner: String,
    }
}

facts_data! {
    /// A selector on a receiver (Python).
    pub struct SelectorData {
        [wire] construct: String,
        [wire] literal: Option<String>,
        [wire] member: Option<String>,
        [wire] operation: Operation,
        [wire] owner: String,
        [wire] receiver_binding: Option<ReceiverBinding>,
        [wire] receiver_parameter: Option<String>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] receiver_parameter_owner: Option<String>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] receiver_parameter_scopes: Option<Vec<BindingScope>>,
        [wire] receiver_type: Option<String>,
        [wire] selector_role: SelectorRole,
        [wire] status: Status,
    }
}

facts_data! {
    /// A numeric operand and its proof (Python).
    pub struct NumericOperandData {
        [read] binding_scopes: Vec<BindingScope>,
        [read] column: i64,
        [read] derivation: Vec<String>,
        [read] end_column: i64,
        [read] end_line: i64,
        [read] form: String,
        [read] line: i64,
        [read] module: ModuleName,
        [read] operation: Operation,
        [read] owner: String,
        [read] proof: Proof,
        [read] subject: Option<String>,
        [read] value: Option<i64>,
    }
}

facts_data! {
    /// A typing signal (Python).
    pub struct SignalData {
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] annotation: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] expression: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] line: Option<i64>,
        [read] owner: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] positions: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] qualified_name: Option<String>,
        [read] signal: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] statement: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] tag: Option<String>,
    }
}
