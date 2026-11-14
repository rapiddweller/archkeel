// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cycle scope of each source profile (AD-500).

use super::Profile;

/// Whether a cycle rule can have its receipt: the collector proves that it sees each local
/// package (`_cycle_scan_coverage`). The Dart survey does not prove it (AD-500).
pub fn proves_cycle_scope(profile: Profile) -> bool {
    match profile {
        Profile::TypeScript | Profile::Rust | Profile::Python => true,
        Profile::Dart => false,
    }
}
