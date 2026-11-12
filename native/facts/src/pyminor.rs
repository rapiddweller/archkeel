// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The supported CPython minors, decoded once with the interpreter version.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PyMinor {
    Py311,
    Py312,
    Py313,
    Py314,
}

impl PyMinor {
    /// Decode a minor at a text boundary. No unsupported minor has a table.
    pub fn decode(text: &str) -> Result<Self, String> {
        match text {
            "11" => Ok(Self::Py311),
            "12" => Ok(Self::Py312),
            "13" => Ok(Self::Py313),
            "14" => Ok(Self::Py314),
            _ => Err(format!(
                "unsupported Python minor {text}; expected Python 3.11 to 3.14"
            )),
        }
    }

    pub fn number(self) -> u8 {
        match self {
            Self::Py311 => 11,
            Self::Py312 => 12,
            Self::Py313 => 13,
            Self::Py314 => 14,
        }
    }
}

/// The original wire text and its checked minor. Serialization keeps the wire unchanged.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct PythonVersion {
    text: String,
    minor: PyMinor,
}

impl PythonVersion {
    pub fn minor(&self) -> PyMinor {
        self.minor
    }

    pub fn as_str(&self) -> &str {
        &self.text
    }
}

impl From<PythonVersion> for String {
    fn from(version: PythonVersion) -> Self {
        version.text
    }
}

impl TryFrom<String> for PythonVersion {
    type Error = String;

    fn try_from(text: String) -> Result<Self, String> {
        let label = "resolver.interpreter.version";
        let Some(("3", minor)) = parts(&text) else {
            return Err(format!(
                "{label} must be a full Python version, such as 3.11.12"
            ));
        };
        let minor = PyMinor::decode(minor).map_err(|error| format!("{label}: {error}"))?;
        Ok(Self { text, minor })
    }
}

fn parts(version: &str) -> Option<(&str, &str)> {
    let mut parts = version.split('.');
    let (major, minor, patch) = (parts.next()?, parts.next()?, parts.next()?);
    if parts.next().is_some() {
        return None;
    }
    let patch = patch.strip_suffix('+').unwrap_or(patch);
    let digits = patch.len() - patch.trim_start_matches(|c: char| c.is_ascii_digit()).len();
    let (number, tag) = patch.split_at(digits);
    let tag_ok = tag.is_empty()
        || ["a", "b", "rc"]
            .iter()
            .any(|kind| tag.strip_prefix(kind).is_some_and(is_number));
    (is_number(major) && is_number(minor) && is_number(number) && tag_ok).then_some((major, minor))
}

fn is_number(text: &str) -> bool {
    !text.is_empty()
        && text.bytes().all(|byte| byte.is_ascii_digit())
        && (text == "0" || !text.starts_with('0'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_supported_minor_selects_only_its_own_rules() {
        for minor in [
            PyMinor::Py311,
            PyMinor::Py312,
            PyMinor::Py313,
            PyMinor::Py314,
        ] {
            let decoded = PyMinor::decode(&minor.number().to_string()).unwrap();
            assert_eq!(decoded, minor);
            let version = PythonVersion::try_from(format!("3.{}.12", minor.number())).unwrap();
            assert_eq!(version.minor(), minor);
            assert_eq!(version.as_str(), format!("3.{}.12", minor.number()));
        }
        for minor in ["10", "15", "999", "oops"] {
            assert!(PyMinor::decode(minor).unwrap_err().contains("Python minor"));
        }
    }
}
