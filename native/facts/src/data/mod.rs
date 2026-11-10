// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of each record kind. One data type serves the kinds that share a shape, for example
//! `ImportData` serves the seven import kinds of TypeScript and the import of Python and Dart.
//!
//! The field sets are the union over the producers (WP1 inventory). A field that one producer does
//! not write is an `Option` that the wire skips. A `[read]` field is in the read-set.

mod constructs;
mod imports;
mod sites;
mod symbols;

pub use constructs::{ConstructData, NumericOperandData, SelectorData, SignalData};
pub use imports::{GapData, ImportData};
pub use sites::{BindingData, CallData, ReferenceData, SourceRoleData, UnusedBindingData};
pub use symbols::{CallableData, ClassData, Declared, ValueData};
