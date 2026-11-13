// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the constructs and typing_signals sections.

use crate::ids::ModuleName;
use crate::nested::{BindingScope, ReceiverBinding};
use crate::vocab::{
    ConstructForm, Operation, PlaceholderForm, Proof, SelectorRole, Signal, Status,
};

facts_data! {
    /// A written construct with no additional fields.
    pub struct PlainConstructData {
        [read] construct: String,
        [read] owner: String,
    }
}

facts_data! {
    /// A function body that declares no implementation.
    pub struct PlaceholderData {
        [read] construct: String,
        [wire] form: PlaceholderForm,
        [read] owner: String,
    }
}

facts_data! {
    /// A written construct that a rule can forbid.
    pub struct ConstructData {
        [read] construct: String,
        [read skip] form: Option<ConstructForm>,
        [read skip] handled: Option<Vec<String>>,
        [read] owner: String,
    }
}

facts_data! {
    /// A selector on a receiver (Python).
    pub struct SelectorData {
        [wire] construct: String,
        [wire required] literal: Option<String>,
        [wire required] member: Option<String>,
        [wire] operation: Operation,
        [wire] owner: String,
        [wire required] receiver_binding: Option<ReceiverBinding>,
        [wire required] receiver_parameter: Option<String>,
        [wire skip] receiver_parameter_owner: Option<String>,
        [wire skip] receiver_parameter_scopes: Option<Vec<BindingScope>>,
        [wire required] receiver_type: Option<String>,
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
        [read required] subject: Option<String>,
        [read required] value: Option<i64>,
    }
}

facts_data! {
    /// A typing signal (Python).
    pub struct SignalData {
        [read skip] annotation: Option<String>,
        [read skip] expression: Option<String>,
        [read skip] line: Option<i64>,
        [read] owner: String,
        [read skip] positions: Option<Vec<String>>,
        [read skip] qualified_name: Option<String>,
        [read] signal: Signal,
        [read skip] statement: Option<String>,
        [read skip] tag: Option<String>,
    }
}
