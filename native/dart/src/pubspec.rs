// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read the package name and the SDK constraint of `pubspec.yaml` without a YAML parser, as
//! `snapshot._pubspec_metadata` of the Python Dart collector does, line by line.

use archkeel_pytext::splitlines;

use crate::module::is_identifier;
use crate::pytext::{is_space, lstrip, strip};

/// The state of the SDK requirement, as `RuntimeRequirementState` names it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "dump", derive(serde::Deserialize))]
#[cfg_attr(feature = "dump", serde(rename_all = "snake_case"))]
pub(crate) enum SdkState {
    Declared,
    #[cfg_attr(feature = "dump", serde(rename = "requirement_missing"))]
    Missing,
    #[cfg_attr(feature = "dump", serde(rename = "requirement_invalid"))]
    Invalid,
}

impl SdkState {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            SdkState::Declared => "declared",
            SdkState::Missing => "requirement_missing",
            SdkState::Invalid => "requirement_invalid",
        }
    }
}

/// The metadata of one `pubspec.yaml`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Pubspec {
    /// The package name, when exactly one valid `name:` line exists.
    pub(crate) name: Option<String>,
    pub(crate) sdk: Option<String>,
    pub(crate) state: SdkState,
}

#[derive(Default)]
struct Counts {
    name: Option<String>,
    sdk: Option<String>,
    names: usize,
    environments: usize,
    sdk_fields: usize,
    invalid: bool,
    // `Some(0)`: the line before opened a block `environment:` at the left margin.
    environment_indent: Option<usize>,
    field_indent: Option<usize>,
}

/// Decode the bytes of `pubspec.yaml`. Bytes that are not UTF-8 give an invalid requirement.
pub(crate) fn read(raw: &[u8]) -> Pubspec {
    let Ok(text) = std::str::from_utf8(raw) else {
        return Pubspec {
            name: None,
            sdk: None,
            state: SdkState::Invalid,
        };
    };
    let mut counts = Counts::default();
    for line in splitlines(text) {
        if is_ignorable(line) {
            continue;
        }
        let indent = line.len() - lstrip(line).len();
        if indent == 0 {
            counts.top_level(line);
        } else if counts.environment_indent == Some(0) {
            counts.environment_field(line, indent);
        }
    }
    counts.finish()
}

impl Counts {
    fn top_level(&mut self, line: &str) {
        if let Some(value) = name_value(line) {
            self.names += 1;
            let value = unquote(strip(value));
            self.name = is_identifier(value).then(|| value.to_owned());
        }
        let (key, value) = match line.split_once(':') {
            Some((key, value)) => (key, Some(value)),
            None => (line, None),
        };
        self.field_indent = None;
        let is_environment = strip(key) == "environment";
        match value {
            Some(value) if is_environment => {
                self.environments += 1;
                let value = strip(value.split('#').next().unwrap_or(""));
                self.environment_indent = value.is_empty().then_some(0);
                self.invalid |= !value.is_empty();
            }
            _ => self.environment_indent = None,
        }
    }

    fn environment_field(&mut self, line: &str, indent: usize) {
        let field_indent = *self.field_indent.get_or_insert(indent);
        let stripped = strip(line);
        let (key, value) = match stripped.split_once(':') {
            Some((key, value)) => (key, Some(value)),
            None => (stripped, None),
        };
        if key != "sdk" {
            return;
        }
        // The indent is a count of characters in Python and of bytes here: white space at the
        // left margin of a YAML line is ASCII in practice, and a non-ASCII space is reported below.
        if indent != field_indent || line[..indent].contains('\t') {
            self.invalid = true;
            return;
        }
        self.sdk_fields += 1;
        let text = strip(value.unwrap_or(""));
        let text = unquote(strip(text.split(" #").next().unwrap_or("")));
        if value.is_none()
            || text.is_empty()
            || text.contains(['{', '}', '[', ']', '&', '*', '!', '|'])
        {
            self.invalid = true;
        } else {
            self.sdk = Some(text.to_owned());
        }
    }

    fn finish(self) -> Pubspec {
        let state = if self.invalid || self.environments > 1 || self.sdk_fields > 1 {
            SdkState::Invalid
        } else if self.sdk_fields == 1 {
            SdkState::Declared
        } else {
            SdkState::Missing
        };
        Pubspec {
            name: self.name.filter(|_| self.names == 1),
            sdk: self.sdk.filter(|_| state != SdkState::Invalid),
            state,
        }
    }
}

/// `\s*(?:#.*)?` matches the whole line: a blank line or a comment.
fn is_ignorable(line: &str) -> bool {
    let rest = lstrip(line);
    rest.is_empty() || rest.starts_with('#')
}

/// `^name\s*:\s*(.*?)\s*(?:#.*)?$`: the value up to the first `#`, without the white space.
fn name_value(line: &str) -> Option<&str> {
    let rest = line.strip_prefix("name")?;
    let rest = rest.trim_start_matches(is_space).strip_prefix(':')?;
    let rest = rest.trim_start_matches(is_space);
    let value = rest.split('#').next().unwrap_or("");
    Some(value.trim_end_matches(is_space))
}

/// `_unquote_scalar`: the text between one pair of the same quotes.
fn unquote(value: &str) -> &str {
    for quote in ['\'', '"'] {
        if value.len() >= 2 && value.starts_with(quote) && value.ends_with(quote) {
            return &value[1..value.len() - 1];
        }
    }
    value
}

#[cfg(test)]
#[path = "pubspec_tests.rs"]
mod tests;
