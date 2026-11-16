// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of each record kind. One data type serves the kinds that share a shape, for example
//! `ImportData` serves the seven import kinds of TypeScript and the import of Python and Dart.
//!
//! The field sets are the union over the producers (WP1 inventory). A field that one producer does
//! not write is an `Option` that the wire skips. A `[read]` field is in the read-set.

mod constructs;
pub(crate) mod door;
pub(crate) mod gap_data;
pub(crate) mod gap_effect;
mod imports;
mod sites;
mod symbols;

pub use constructs::ConstructData;
pub use constructs::NumericOperandData;
pub use constructs::PlaceholderData;
pub use constructs::PlainConstructData;
pub use constructs::SelectorData;
pub use constructs::SignalData;
pub use door::DoorForm;
pub use door::DoorSite;
pub use gap_data::GapData;
pub use gap_effect::GapEffect;
pub use imports::ImportData;
pub use sites::BindingData;
pub use sites::CallData;
pub use sites::ReferenceData;
pub use sites::SourceRoleData;
pub use sites::UnusedBindingData;
pub use symbols::CallableData;
pub use symbols::ClassData;
pub use symbols::Declared;
pub use symbols::ValueData;
