// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the constructs and typing_signals sections.

use crate::ids::ModuleName;
use crate::nested::{BindingScope, ReceiverBinding};
use crate::vocab::{ConstructForm, Operation, Proof, SelectorRole, Signal, Status};

facts_data! {
    /// A written construct that a rule can forbid.
    pub struct ConstructData {
        [read] construct: String,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] form: Option<ConstructForm>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] handled: Option<Vec<String>>,
        [read] owner: String,
    }
}

facts_data! {
    /// A selector on a receiver (Python).
    pub struct SelectorData {
        [wire] construct: String,
        [wire] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] literal: Option<String>,
        [wire] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] member: Option<String>,
        [wire] operation: Operation,
        [wire] owner: String,
        [wire] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] receiver_binding: Option<ReceiverBinding>,
        [wire] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] receiver_parameter: Option<String>,
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] receiver_parameter_owner: Option<String>,
        [wire skip] #[serde(default, skip_serializing_if = "Option::is_none")] receiver_parameter_scopes: Option<Vec<BindingScope>>,
        [wire] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] receiver_type: Option<String>,
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
        [read] form: ConstructForm,
        [read] line: i64,
        [read] module: ModuleName,
        [read] operation: Operation,
        [read] owner: String,
        [read] proof: Proof,
        [read] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] subject: Option<String>,
        [read] #[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)] value: Option<i64>,
    }
}

facts_data! {
    /// A typing signal (Python).
    pub struct SignalData {
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] annotation: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] expression: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] line: Option<i64>,
        [read] owner: String,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] positions: Option<Vec<String>>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] qualified_name: Option<String>,
        [read] signal: Signal,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] statement: Option<String>,
        [read skip] #[serde(default, skip_serializing_if = "Option::is_none")] tag: Option<String>,
    }
}
