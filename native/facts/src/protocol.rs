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
        /// Protocol 3, the oldest request.
        V3 = "3.0.0",
        /// Protocol 8.
        V8 = "8.0.0",
        /// Protocol 9: the scope can exclude test sources.
        V9 = "9.0.0",
        /// Protocol 10: the request of the native Python collector.
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
    /// has no compressed reply of its own. Each native collector writes the 11.0.0 reply, which
    /// carries the validation block of its facts (AD-688). A 3.0.0 request is answered as 8.0.0
    /// (`reply_version`), so it gets the 11.0.0 reply too.
    pub fn compressed(self) -> Option<ProtocolVersion> {
        match self {
            Self::V3 => None,
            Self::V8 | Self::V9 | Self::V10 => Some(ProtocolVersion::V11),
        }
    }
}

/// The request version that a collector answers for a request version: a 3.0.0 request is read as
/// 8.0.0. The compressed reply of each is 11.0.0 (`Version::compressed`, AD-688).
pub fn reply_version(request: Version) -> Version {
    match request {
        Version::V3 | Version::V8 => Version::V8,
        Version::V9 => Version::V9,
        Version::V10 => Version::V10,
    }
}
