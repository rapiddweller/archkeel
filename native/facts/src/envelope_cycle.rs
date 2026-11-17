// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cycle scope of each source profile (AD-500).

use super::Profile;

/// Whether a cycle rule can have its receipt: the collector proves that it sees each local
/// package (`_cycle_scan_coverage`), or states a gap where it does not. The Dart survey proves it
/// from its package map since AD-800 (AD-500 item 8): each import of a package that the map does
/// not prove external is a gap.
pub fn proves_cycle_scope(profile: Profile) -> bool {
    match profile {
        Profile::TypeScript | Profile::Rust | Profile::Python | Profile::Dart => true,
    }
}
