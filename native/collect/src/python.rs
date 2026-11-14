// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python part of the composition (AD-450): the interpreter block of the request and the
//! binding of the reply digests to the files of the snapshot.
//!
//! The core runs no Python interpreter. The request names the grammar of the newest supported
//! minor and the names that are standard in each supported minor (the pinned table of AD-388).
//! A name of only some minors is not standard, so the collector gives it as an external package.

use archkeel_facts::envelope::{Input, Profile, Reply};
use archkeel_facts::identity::sha256_hex;
use serde_json::{json, Value};

use crate::repository::{Over, Root};

/// The grammar of the survey: the newest minor that the collector supports. It is a parse
/// setting, not the version of an interpreter that ran.
pub(crate) const GRAMMAR: &str = "3.14.0";

/// The largest input that the snapshot reads (AD-319); a larger file is no input.
const MAX_INPUT_BYTES: u64 = 4 << 20;

/// The resolver of a Python request: the import survey with the pinned interpreter block.
pub(crate) fn resolver() -> Value {
    json!({
        "language": "python",
        "phase": "imports",
        "interpreter": {
            "version": GRAMMAR,
            "stdlib_module_names": archkeel_store::standard_library_everywhere(Profile::Python),
            "builtin_module_names": [],
        },
    })
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
        let bytes = match root.read(&input.path, MAX_INPUT_BYTES) {
            Ok(Some((_, bytes))) => bytes,
            Ok(None) | Err(Over(_)) => {
                return Err(format!("the input {} cannot be read again", input.path))
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
