// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The collection protocol versions that a native collector reads and writes.

/// A request version that the host sends to a TypeScript collector.
///
/// The host sends 3.0.0 to an explicit `collector_argv` and 8.0.0 to its built-in collector.
/// Version 9.0.0 adds `scope.exclude_test_sources` (AD-313).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Version {
    V3,
    V8,
    V9,
}

impl Version {
    pub fn parse(text: &str) -> Option<Self> {
        match text {
            "3.0.0" => Some(Self::V3),
            "8.0.0" => Some(Self::V8),
            "9.0.0" => Some(Self::V9),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::V3 => "3.0.0",
            Self::V8 => "8.0.0",
            Self::V9 => "9.0.0",
        }
    }

    /// Whether the request scope carries `exclude_test_sources`.
    pub fn has_test_scope(self) -> bool {
        self == Self::V9
    }
}

/// The one place that chooses the reply version for a request version.
///
/// The host requires the request version back when it pins a version: 8.0.0 for its built-in
/// collector, 9.0.0 for a test-scoped request. For an explicit `collector_argv` it accepts any
/// valid reply, so a 3.0.0 request gets the compressed 8.0.0 reply. 8.0.0 and 9.0.0 replies
/// have the same shape.
pub fn reply_version(request: Version) -> Version {
    match request {
        Version::V3 | Version::V8 => Version::V8,
        Version::V9 => Version::V9,
    }
}
