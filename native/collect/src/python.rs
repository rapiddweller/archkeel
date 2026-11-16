// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python part of the composition (AD-450): the interpreter block of the request and the
//! binding of the reply digests to the files of the snapshot.
//!
//! The core runs no Python interpreter. The request names the selected target grammar and its
//! pinned standard-library table (AD-634).

use archkeel_facts::envelope::RequirementState;
use archkeel_facts::envelope::{Input, Profile, Reply};
use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::Snapshot;
use serde_json::{json, Value};

use crate::repository::{Over, Root};

/// The default grammar of the survey, not the version of an interpreter that ran.
pub(crate) const GRAMMAR: &str = "3.14.0";

/// The largest input that the snapshot reads (AD-319); a larger file is no input.
const MAX_INPUT_BYTES: u64 = 4 << 20;

/// The resolver of a Python request: the target grammar and its pinned standard-library names.
pub(crate) fn resolver(version: &str) -> Value {
    json!({
        "language": "python",
        "phase": "imports",
        "interpreter": {
            "version": version,
            "stdlib_module_names": archkeel_store::standard_library_at(Profile::Python, version)
                .unwrap_or_default(),
            "builtin_module_names": [],
        },
    })
}

/// Select a supported Python target, without starting an interpreter.
pub(crate) fn target(root: &Root, configured: Option<&str>) -> Result<(String, String), String> {
    let root_text = root.path().to_str().ok_or("the root is not UTF-8")?;
    let mut snapshot = Snapshot::new(root_text);
    let (requirement, state) = archkeel_python_collector::python_requirement(&mut snapshot);
    let (version, source) = if let Some(value) = configured {
        let source = requirement.as_ref().map_or_else(
            || "scan.python in archkeel.toml".to_owned(),
            |required| {
                format!(
                    "scan.python in archkeel.toml; requires-python {required:?} in pyproject.toml"
                )
            },
        );
        let selected = (value.split('.').count() == 2)
            .then(|| version(value))
            .flatten();
        (selected, source)
    } else if let Some(required) = requirement {
        let lower = lower_bound(&required)
            .ok_or_else(|| format!("cannot read requires-python {required:?}; set scan.python"))?;
        (
            Some(lower),
            format!("requires-python {required:?} in pyproject.toml"),
        )
    } else if matches!(
        state,
        RequirementState::MetadataMissing | RequirementState::RequirementMissing
    ) {
        (version(GRAMMAR), "the collector default".to_owned())
    } else {
        return Err("cannot read the Python requirement; set scan.python".to_owned());
    };
    let Some([3, minor @ 11..=14, patch]) = version else {
        let wanted = version.map_or_else(
            || configured.unwrap_or("an unknown version").to_owned(),
            |[major, minor, patch]| format!("{major}.{minor}.{patch}"),
        );
        return Err(format!("Python target {wanted} is unsupported; the collector supports Python 3.11–3.14; set python = \"3.13\" in [scan]"));
    };
    Ok((format!("3.{minor}.{patch}"), format!("ArchKeel reads this project as Python 3.{minor} (from {source}); the collector supports Python 3.11–3.14")))
}

/// Read only numeric `>=` and `<` clauses; all other requirement forms remain undecided.
fn lower_bound(required: &str) -> Option<[u32; 3]> {
    let mut lower = None;
    for clause in required.split(',').map(str::trim) {
        if let Some(value) = clause.strip_prefix(">=") {
            let found = version(value)?;
            lower = Some(lower.map_or(found, |old: [u32; 3]| old.max(found)));
        } else {
            version(clause.strip_prefix('<')?)?;
        }
    }
    lower
}

/// The numeric release parts of a target or requirement bound.
fn version(text: &str) -> Option<[u32; 3]> {
    let mut parts = text.trim().split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next().map(str::parse).transpose().ok()?.unwrap_or(0);
    if parts.next().is_some() {
        return None;
    }
    Some([major, minor, patch])
}

/// Read each input of the reply again from the snapshot. Each digest and the source digest must
/// be the digest of the bytes there; else the reply describes other bytes and gives no verdict.
pub(crate) fn bound(root: &Root, reply: &Reply) -> Result<(), String> {
    let mut source = Vec::new();
    reread(root, reply, |path, bytes| {
        source.extend_from_slice(path.as_bytes());
        source.push(0);
        source.extend_from_slice(bytes);
        source.push(0);
    })?;
    if reply.facts.source.source_digest != sha256_hex(&source) {
        return Err("the source digest differs from the inputs".to_owned());
    }
    Ok(())
}

/// Read each input of the reply again, in path order: its bytes must have its digest. `each`
/// sees the path and the bytes of each input (AD-450, AD-468).
pub(crate) fn reread(
    root: &Root,
    reply: &Reply,
    mut each: impl FnMut(&str, &[u8]),
) -> Result<(), String> {
    let mut inputs: Vec<&Input> = reply.facts.inputs.iter().collect();
    inputs.sort_by(|left, right| left.path.cmp(&right.path));
    for input in inputs {
        // AD-538: the path of a listing input ends with `/`; its bytes are the sorted names.
        let bytes = if input.path.ends_with('/') {
            let text = root.names_of(&input.path);
            text.map(String::into_bytes)
                .ok_or_else(|| format!("the input {} cannot be read again", input.path))?
        } else {
            match root.read(&input.path, MAX_INPUT_BYTES) {
                Ok(Some((_, bytes))) => bytes,
                Ok(None) | Err(Over(_)) => {
                    return Err(format!("the input {} cannot be read again", input.path))
                }
            }
        };
        if sha256_hex(&bytes) != input.digest {
            return Err(format!("the input {} differs from its digest", input.path));
        }
        each(&input.path, &bytes);
    }
    Ok(())
}

#[cfg(test)]
#[path = "python_tests.rs"]
mod tests;
