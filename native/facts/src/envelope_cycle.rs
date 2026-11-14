// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cycle scope of each source profile (AD-496).

use super::Profile;

impl Profile {
    /// Whether a cycle rule can have its receipt: the collector proves that it sees each local
    /// package (`_cycle_scan_coverage`). The Dart survey does not prove it (AD-496).
    pub fn proves_cycle_scope(self) -> bool {
        match self {
            Profile::TypeScript | Profile::Rust | Profile::Python => true,
            Profile::Dart => false,
        }
    }
}
