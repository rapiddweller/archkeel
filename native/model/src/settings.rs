// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the shell tells the core about a run (AD-372): the namespace of the configuration and
//! the top-level names of the standard library of the reply's profile.
//!
//! The shell is the only reader of the configuration and owns the table of profiles. The core
//! parses no configuration file and names no language, so it takes both as typed values.

use std::collections::BTreeSet;

/// The settings of one run.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Settings {
    namespace: String,
    standard_library: BTreeSet<String>,
}

impl Settings {
    /// The settings of a namespace and the standard library names of the profile.
    pub fn new(namespace: String, standard_library: impl IntoIterator<Item = String>) -> Self {
        Settings {
            namespace,
            standard_library: standard_library.into_iter().collect(),
        }
    }

    /// The dotted namespace of the configuration.
    pub fn namespace(&self) -> &str {
        &self.namespace
    }

    /// True when `root` is a top-level name of the standard library of the profile.
    pub fn standard(&self, root: &str) -> bool {
        self.standard_library.contains(root)
    }
}
