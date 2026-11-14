// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The native TypeScript collector of Archkeel as a library (AD-406).
//!
//! Two callers run one collection: the binary `archkeel-typescript-collector` (`main.rs`), which
//! the host starts as a subprocess and which writes the compressed reply to stdout (`reply`), and
//! the crate `archkeel-collect`, which runs the collector in the process of the core and takes the
//! typed reply (`typed_reply`). Both run the same `gather` and the same producer of the records
//! (`records::plan`); only the sink differs.

#![forbid(unsafe_code)]
#![deny(unreachable_pub)]

mod ancestors;
mod bound_names;
mod cited;
mod class_data;
mod class_members;
mod collect;
mod collected;
mod concerns;
mod config;
mod construct_records;
mod constructors;
mod definitions;
mod discover;
#[cfg(feature = "dump")]
pub mod dump;
mod exports;
mod glob;
mod import_bindings;
mod installed;
mod jsdoc;
mod kept;
mod kept_script;
mod kinds;
mod layer;
mod layout;
mod manifest;
mod members;
mod options;
mod options_target;
mod parse;
mod places;
mod plant;
mod pytext;
mod records;
#[cfg(any(test, feature = "dump"))]
mod records_lists;
mod references;
mod resolution;
mod resolve;
mod scan;
mod scope;
mod script;
mod script_alias;
mod script_bind;
mod script_code;
mod script_declarations;
mod script_declare;
mod script_depend;
mod script_deps;
mod script_effects;
mod script_environment;
mod script_factory;
mod script_flags;
mod script_global;
mod script_index;
mod script_names;
mod script_namespace;
mod script_project;
mod script_proof;
mod script_publish;
mod script_records;
mod script_refs;
mod script_scope;
mod script_syntax;
mod script_types;
mod script_vendor;
mod script_window;
mod script_wrapper;
mod script_writes;
mod site_names;
mod site_paths;
mod site_records;
mod site_syntax;
mod site_text;
mod site_types;
mod sites;
mod source;
mod source_input;
mod std_globals;
mod symbol_table;
mod symbols;
mod syntax;
mod test_sources;
mod tree;
mod umd;
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
mod umd_publication;
mod walk;

use archkeel_facts::envelope::{Profile, Provenance, Reply};
use archkeel_facts::request::TypeScriptRequest;
use archkeel_wire::protocol::Version;

pub use crate::collect::reply;

/// The test features that this build of the collector has. A build with one of them reads the
/// planted faults of `plant.rs` from the environment, so `archkeel-collect` refuses its facts
/// (AD-406). The release build has none.
pub const TEST_FEATURES: &[&str] = if cfg!(feature = "dump") {
    &["dump"]
} else {
    &[]
};

/// The provenance of this build: the collector of the TypeScript profile with the code digest of
/// the workspace.
pub fn provenance() -> Provenance {
    Provenance::native(
        Profile::TypeScript,
        (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
        (
            env!("ARCHKEEL_RUSTC_VERSION"),
            env!("CARGO_PKG_RUST_VERSION"),
        ),
    )
}

/// The typed reply of one request: the same facts that `reply` writes as compressed bytes.
pub fn typed_reply(
    request: &TypeScriptRequest,
    provenance: Provenance,
    version: Version,
) -> Result<Reply, String> {
    let (facts, pending) = collect::gather(request, provenance);
    let reply = records::typed_reply(version, facts, &pending);
    drop(pending);
    reply
}
