// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Rust collector library and the subprocess producer share one collection (AD-406).

#![forbid(unsafe_code)]
#![deny(unreachable_pub)]

#[cfg(test)]
mod attribute_gap_tests;
mod attrs;
mod builder;
mod collect;
mod crates;
mod declared;
mod definitions;
mod derive_identity;
mod edges;
mod edges_extracted;
mod impl_edges;
mod impl_globs;
#[cfg(test)]
mod known_derive_tests;
mod manifest;
mod manifest_lines;
mod module_edges;
mod modules;
mod modules_alias;
mod nesting;
mod net;
mod paths;
mod plant;
mod registry;
mod reply;
mod resolve;
mod scan;
mod site;
mod source;
mod symbols;
mod test_scope;
mod tokens;
mod toml;
mod tree;

use archkeel_facts::envelope::{Profile, Provenance, Reply};
use archkeel_facts::request::RustRequest;
use archkeel_wire::protocol::Version;

/// Test features read planted faults. The composition refuses a build with one.
pub const TEST_FEATURES: &[&str] = if cfg!(feature = "dump") {
    &["dump"]
} else {
    &[]
};

/// The provenance of this linked collector and its workspace source digest.
pub fn provenance() -> Provenance {
    Provenance::native(
        Profile::Rust,
        (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
        (
            env!("ARCHKEEL_RUSTC_VERSION"),
            env!("CARGO_PKG_RUST_VERSION"),
        ),
    )
}

/// The compressed reply of the subprocess path.
pub fn reply(
    request: &RustRequest,
    provenance: Provenance,
    version: Version,
) -> Result<Vec<u8>, String> {
    collect::collect(request, provenance).encode(version)
}

/// The same records through the typed sink, without reply bytes from a caller.
pub fn typed_reply(
    request: &RustRequest,
    provenance: Provenance,
    version: Version,
) -> Result<Reply, String> {
    collect::collect(request, provenance).typed(version)
}
