// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one list of the collection protocol versions that a native collector reads and writes.
//!
//! The host sends 3.0.0 to an explicit `collector_argv` and 8.0.0 to its built-in collector.
//! Version 9.0.0 adds `scope.exclude_test_sources` (AD-313). Version 10.0.0 is the request of the
//! native Python collector: the Python resolver with the interpreter block (AD-334). `Version::ALL`
//! is the list that the request schema, the reply encoder and the Python host share
//! (`tests/test_native_versions.py`).

use crate::envelope::ProtocolVersion;

closed! {
    /// A request version that the host sends to a native collector.
    pub enum Version {
        V3 = "3.0.0",
        V8 = "8.0.0",
        V9 = "9.0.0",
        V10 = "10.0.0",
    }
}

impl Version {
    /// Whether the request scope carries `exclude_test_sources`.
    pub fn has_test_scope(self) -> bool {
        matches!(self, Self::V9 | Self::V10)
    }

    /// Whether the request is for the native Python collector. Only 10.0.0 carries the Python
    /// resolver, and 10.0.0 carries no other resolver.
    pub fn is_python(self) -> bool {
        self == Self::V10
    }

    /// The version of the compressed reply for this request version, or `None` when the version
    /// has no compressed reply of its own. The host requires the request version back when it
    /// pins one: 8.0.0 for its built-in collector, 9.0.0 for a test-scoped request. An explicit
    /// `collector_argv` accepts any valid reply, so a 3.0.0 request gets the 8.0.0 reply.
    pub fn compressed(self) -> Option<ProtocolVersion> {
        match self {
            Self::V3 => None,
            Self::V8 => Some(ProtocolVersion::V8),
            Self::V9 => Some(ProtocolVersion::V9),
            Self::V10 => Some(ProtocolVersion::V10),
        }
    }
}

/// The one place that chooses the reply version for a request version. 8.0.0 and 9.0.0 replies
/// have the same shape. A 10.0.0 request gets the 10.0.0 reply, which has the shape of 9.0.0.
pub fn reply_version(request: Version) -> Version {
    match request {
        Version::V3 | Version::V8 => Version::V8,
        Version::V9 => Version::V9,
        Version::V10 => Version::V10,
    }
}
