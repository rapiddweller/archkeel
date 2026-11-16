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
        /// The name of the construct.
        [read] construct: String,
        /// The qualified name of the symbol that owns it.
        [read] owner: String,
    }
}

facts_data! {
    /// A function body that declares no implementation.
    pub struct PlaceholderData {
        /// The name of the construct.
        [read] construct: String,
        /// The form in which the construct is written.
        [wire] form: PlaceholderForm,
        /// The qualified name of the symbol that owns it.
        [read] owner: String,
    }
}

facts_data! {
    /// A written construct that a rule can forbid.
    pub struct ConstructData {
        /// The name of the construct.
        [read] construct: String,
        /// The form in which the construct is written.
        [read skip] form: Option<ConstructForm>,
        /// The cases that the construct handles.
        [read skip] handled: Option<Vec<String>>,
        /// The qualified name of the symbol that owns it.
        [read] owner: String,
    }
}

facts_data! {
    /// A selector on a receiver (Python).
    pub struct SelectorData {
        /// The name of the construct that the selector observes.
        [wire] construct: String,
        /// The literal that the selector reads.
        [wire required] literal: Option<String>,
        /// The member that the selector reads.
        [wire required] member: Option<String>,
        /// The operation that the site performs.
        [wire] operation: Operation,
        /// The qualified name of the symbol that owns it.
        [wire] owner: String,
        /// What the receiver binds to.
        [wire required] receiver_binding: Option<ReceiverBinding>,
        /// The parameter that holds the receiver.
        [wire required] receiver_parameter: Option<String>,
        /// The owner of that parameter.
        [wire skip] receiver_parameter_owner: Option<String>,
        /// The scopes that bind that parameter.
        [wire skip] receiver_parameter_scopes: Option<Vec<BindingScope>>,
        /// The type of the receiver as written.
        [wire required] receiver_type: Option<String>,
        /// The role of the selector.
        [wire] selector_role: SelectorRole,
        /// The proof state of the record.
        [wire] status: Status,
    }
}

facts_data! {
    /// A numeric operand and its proof (Python).
    pub struct NumericOperandData {
        /// The scopes that bind the operand.
        [read] binding_scopes: Vec<BindingScope>,
        /// The first column of the place.
        [read] column: i64,
        /// The steps that derive the value.
        [read] derivation: Vec<String>,
        /// The last column of the place.
        [read] end_column: i64,
        /// The last line of the place.
        [read] end_line: i64,
        /// The form in which the construct is written.
        [read] form: ConstructForm,
        /// The first line of the place, counted from 1.
        [read] line: i64,
        /// The module that holds it.
        [read] module: ModuleName,
        /// The operation that the site performs.
        [read] operation: Operation,
        /// The qualified name of the symbol that owns it.
        [read] owner: String,
        /// The proof of the value.
        [read] proof: Proof,
        /// The subject of the operand.
        [read required] subject: Option<String>,
        /// The value as written.
        [read required] value: Option<i64>,
    }
}

facts_data! {
    /// A typing signal (Python).
    pub struct SignalData {
        /// The annotation as written.
        [read skip] annotation: Option<String>,
        /// The expression as written.
        [read skip] expression: Option<String>,
        /// The first line of the place, counted from 1.
        [read skip] line: Option<i64>,
        /// The qualified name of the symbol that owns it.
        [read] owner: String,
        /// The positions that the signal covers.
        [read skip] positions: Option<Vec<String>>,
        /// The name with the names of its parents.
        [read skip] qualified_name: Option<String>,
        /// The kind of the typing signal.
        [read] signal: Signal,
        /// The statement of the signal.
        [read skip] statement: Option<String>,
        /// The tag of the signal.
        [read skip] tag: Option<String>,
    }
}
