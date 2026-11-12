// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the shell tells the core about a run (AD-372): the namespace of the configuration, the
//! profile of the reply and the top-level names of the standard library of that profile.
//!
//! The shell is the only reader of the configuration and owns the table of profiles. The core
//! parses no configuration file and names no language, so it takes these as typed values. It
//! binds them to the reply by a check (`check`, `Model::derive`): the profile must be the profile
//! of the reply, and each module of the reply must lie in the namespace.
//!
//! Slice S4 adds the producer of the reply (AD-344, AD-378): only the host starts the collector,
//! so only the shell knows it. The default is the sound one: a reply of an external collector,
//! which gives no PASS.

use crate::ownership::in_scope;
use crate::reason::Refusal;

/// The largest number of standard library names that a request can carry.
pub const STANDARD_LIBRARY_LIMIT: usize = 1024;
/// The longest standard library name in bytes.
pub const STANDARD_NAME_LIMIT: usize = 128;

/// The settings of one run.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Settings {
    namespace: String,
    profile: String,
    standard_library: Vec<String>,
    producer: Producer,
}

/// Who produced the reply, as the host decides it (`cli/observe.py` `observer_for`).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Producer {
    /// A collector that the host does not trust for a PASS: an external command without a
    /// pinned digest, or a producer that the shell does not name.
    #[default]
    External,
    /// The bundled collector, or an external command with a pinned digest.
    Trusted,
}

impl Settings {
    /// The settings of a namespace, the profile that the shell read and its standard library.
    pub fn new(namespace: String, profile: String, standard_library: Vec<String>) -> Self {
        Settings {
            namespace,
            profile,
            standard_library,
            producer: Producer::External,
        }
    }

    /// The same settings with the producer of the reply.
    pub fn with_producer(self, producer: Producer) -> Self {
        Settings { producer, ..self }
    }

    /// The producer of the reply.
    pub fn producer(&self) -> Producer {
        self.producer
    }

    /// The dotted namespace of the configuration.
    pub fn namespace(&self) -> &str {
        &self.namespace
    }

    /// True when `root` is a top-level name of the standard library of the profile.
    pub fn standard(&self, root: &str) -> bool {
        self.standard_library.iter().any(|name| name == root)
    }

    /// The settings refused by name, unless they hold for a reply of `profile`.
    pub(crate) fn check(&self, profile: &str) -> Result<(), Refusal> {
        if self.profile != profile {
            return Err(Refusal::ProfileMismatch);
        }
        let names = &self.standard_library;
        if names.len() > STANDARD_LIBRARY_LIMIT {
            return Err(Refusal::StandardLibrary("more names than the limit"));
        }
        if names
            .iter()
            .any(|name| name.is_empty() || name.len() > STANDARD_NAME_LIMIT || name.contains('\0'))
        {
            return Err(Refusal::StandardLibrary("an empty, long or NUL name"));
        }
        let mut sorted: Vec<&str> = names.iter().map(String::as_str).collect();
        sorted.sort_unstable();
        if sorted.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(Refusal::StandardLibrary("a duplicate name"));
        }
        Ok(())
    }

    /// The module refused by name, unless it and its package lie in the namespace
    /// (`evaluate_source` raises a protocol error for the same files).
    pub(crate) fn admits(&self, module: &str, package: &str) -> Result<(), Refusal> {
        let namespace = self.namespace.as_str();
        let inside = in_scope(module, namespace)
            && in_scope(module, package)
            && (in_scope(package, namespace) || in_scope(namespace, package));
        if inside {
            Ok(())
        } else {
            Err(Refusal::OutsideNamespace(module.to_owned()))
        }
    }
}

#[cfg(test)]
#[path = "settings_tests.rs"]
mod tests;
