// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python collector library: the import survey of one 10.0.0 request (AD-334, AD-450).
//!
//! The core links this library through `archkeel-collect` and takes the typed reply. The binary
//! is a thin caller: it reads a request on stdin and writes the compressed reply of the same
//! survey. Both paths use one survey and one record producer (`reply.rs`).

#![forbid(unsafe_code)]

#[cfg(feature = "dump")]
pub mod dump;
mod reply;

mod survey;
// AD-377: the definition table and its bases have no caller in the reply yet; the test dump reads
// them. The slice that writes the section `symbols` builds them into the release binary.
#[cfg(any(test, feature = "dump"))]
mod bindings;
#[cfg(any(test, feature = "dump"))]
mod symbols;
#[cfg(any(test, feature = "dump"))]
mod unparse;

mod module;
#[cfg(any(test, feature = "dump"))]
mod pyast;

mod discover;
mod inputs;
mod names;
mod parse;
mod requirement;

mod source;

use archkeel_facts::envelope::{LimitSupport, ProfileLimits, Reply};
use archkeel_facts::request::PythonRequest;

pub use crate::reply::Build;

/// Test features read planted inputs. The composition refuses a build with one.
pub const TEST_FEATURES: &[&str] = if cfg!(feature = "dump") {
    &["dump"]
} else {
    &[]
};

/// The version and the code digest of this build (`archkeel-build-support`).
pub const BUILD: Build<'static> = Build {
    version: env!("ARCHKEEL_VERSION"),
    code_digest: env!("ARCHKEEL_CODE_DIGEST"),
};

/// The compressed reply of the subprocess path.
pub fn compressed_reply(request: &PythonRequest, build: &Build<'_>) -> Result<Vec<u8>, String> {
    reply::reply(request, survey::survey(request)?, build)
}

/// The same survey through the typed sink, without reply bytes from a caller. The linked reply
/// states that the survey reads no symbol selector and no module interface (AD-426, AD-450).
pub fn typed_reply(request: &PythonRequest, build: &Build<'_>) -> Result<Reply, String> {
    let mut reply = reply::typed(request, survey::survey(request)?, build)?;
    reply.facts.profile_limits = Some(ProfileLimits {
        dependency_symbols: LimitSupport::Unsupported,
        interface_boundary: LimitSupport::Unsupported,
    });
    Ok(reply)
}

#[cfg(test)]
fn test_minor(number: u32) -> archkeel_facts::pyminor::PyMinor {
    archkeel_facts::pyminor::PyMinor::decode(&number.to_string()).expect("supported test minor")
}

#[cfg(test)]
fn test_module(text: &str, minor: u32) -> module::Module {
    module::Module::new(
        "app/probe.py".into(),
        "app.probe".into(),
        text.into(),
        test_tree(text, minor).expect("fixture parses"),
    )
}

/// Isolated tree-reader tests also use compiler-invalid ASTs. The request path never calls this.
#[cfg(test)]
fn test_tree(text: &str, minor: u32) -> Result<ruff_python_ast::ModModule, String> {
    use ruff_python_parser::{parse_unchecked, Mode, ParseOptions};
    let version = ruff_python_ast::PythonVersion {
        major: 3,
        minor: test_minor(minor).number(),
    };
    let parsed = parse_unchecked(
        text,
        ParseOptions::from(Mode::Module).with_target_version(version),
    );
    if !parsed.errors().is_empty() || !parsed.unsupported_syntax_errors().is_empty() {
        return Err("invalid probe syntax".to_owned());
    }
    parsed
        .try_into_module()
        .map(|module| module.into_syntax())
        .ok_or_else(|| "not a module".to_owned())
}
