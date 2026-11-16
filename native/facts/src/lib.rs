// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one typed definition of each collector fact that crosses the process boundary (AD-345).
//!
//! A collector builds these types, and the same types give two JSON forms:
//!
//! 1. The protocol 9 wire (`serde::Serialize`). For the native TypeScript collector it is
//!    byte-equal to the reply of today, so it adopts the types without a change of the wire. A
//!    Python or Dart reply decodes and encodes to an equal value, not to equal bytes: Python sorts
//!    the keys, and the types write them in the order of the declaration.
//!
//! `schema::schema` generates the JSON schema of the wire from the types. The committed schema
//! never changes: a change of a type that changes the schema fails `schema_tests`.
//!
//! The vocabularies are closed enums. A value that the protocol does not know is an error, not a
//! string. A field that the wire always writes, also as `null`, must be present. The ids have no
//! conversion between them (`ids`).

// AD-327: a public item that no other crate can reach is a lie in a library.
#![deny(unreachable_pub)]

#[cfg(test)]
mod construct_golden_tests;

#[macro_use]
mod macros;

pub mod data;
pub mod envelope;
mod envelope_vocab;
pub mod fields;
mod gap;
pub mod identity;
pub mod ids;
pub mod measures;
pub mod nested;
pub mod nullable;
mod printable;
pub mod profile_traits;
pub mod protocol;
pub mod pyminor;
pub mod pyrepr;
pub mod reason;
pub mod record;
pub mod request;
pub mod schema;
pub mod sections;
mod skip;
pub mod type_shape;
pub mod vocab;
mod vocab_constructs;

pub use record::{FactData, Record};
pub use sections::{
    BindingFact, CallFact, ConstructFact, GapFact, ImportFact, IntoSection, ReferenceFact, Section,
    SymbolFact,
};

/// The provenance of a linked native collector of `profile` (a variant of
/// [`envelope::Profile`]). The four values come from the build script of the crate that calls it:
/// `env!` expands where the macro expands.
#[macro_export]
macro_rules! native_provenance {
    ($profile:ident) => {
        $crate::envelope::Provenance::native(
            $crate::envelope::Profile::$profile,
            (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
            (
                env!("ARCHKEEL_RUSTC_VERSION"),
                env!("CARGO_PKG_RUST_VERSION"),
            ),
        )
    };
}
