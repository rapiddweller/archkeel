// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scope of a run as a type: complete, or open with the reason that holds back each PASS.

use archkeel_model::Reason;
use serde::Serialize;

/// The scope of a run: complete, or open with the reason that holds back each PASS. The frame
/// writes the word `complete` or the text of the reason (AD-564).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RunScope {
    /// Every part of the scope is proven.
    Complete,
    /// The scope is not proven, for this reason.
    Open(Reason),
}

impl RunScope {
    /// True when every part of the scope is proven.
    pub(crate) fn is_complete(&self) -> bool {
        matches!(self, RunScope::Complete)
    }

    /// The word of the frame: `complete`, or the text of the reason.
    pub(crate) fn word(&self) -> String {
        match self {
            RunScope::Complete => "complete".to_owned(),
            RunScope::Open(reason) => reason.to_string(),
        }
    }
}

impl schemars::JsonSchema for RunScope {
    fn inline_schema() -> bool {
        true
    }

    fn schema_name() -> std::borrow::Cow<'static, str> {
        "RunScope".into()
    }

    fn json_schema(generator: &mut schemars::SchemaGenerator) -> schemars::Schema {
        String::json_schema(generator)
    }
}

impl Serialize for RunScope {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.word())
    }
}

#[cfg(test)]
#[path = "run_scope_tests.rs"]
mod tests;
