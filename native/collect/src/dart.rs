// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Dart part of the composition (AD-468): the request of the import survey and the binding
//! of the reply digests to the files of the snapshot.

use archkeel_facts::envelope::{source_digest, Reply};
use serde_json::{json, Value};

use crate::python::reread;
use crate::repository::Root;

/// The resolver of a Dart request: the survey has no settings.
pub(crate) fn resolver() -> Value {
    json!({"language": "dart"})
}

/// Read each input of the reply again (`python::reread`). The source digest of a Dart reply is
/// the digest of its input listing, so it must agree with the inputs that were read again.
pub(crate) fn bound(root: &Root, reply: &Reply) -> Result<(), String> {
    reread(root, reply, |_, _| {})?;
    if reply.facts.source.source_digest != source_digest(&reply.facts.inputs) {
        return Err("the source digest differs from the inputs".to_owned());
    }
    Ok(())
}

#[cfg(test)]
#[path = "dart_tests.rs"]
mod tests;
