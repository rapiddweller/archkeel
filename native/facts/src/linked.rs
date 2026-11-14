// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The build identity of a collector that `archkeel-collect` links (AD-406, AD-466).

/// Declare `TEST_FEATURES` and `provenance()` of a linked collector crate for `$profile`.
///
/// The macro expands in the collector crate, so `cfg!` reads the features of that crate and
/// `env!` reads the build identity that its `build.rs` records (`archkeel-build-support`). One
/// macro keeps the collectors equal without a copy in each crate.
#[macro_export]
macro_rules! linked_collector {
    ($profile:expr) => {
        /// The test features of this build. A build with one of them reads planted faults, so
        /// `archkeel-collect` refuses its facts (AD-406). The release build has none.
        pub const TEST_FEATURES: &[&str] = if cfg!(feature = "dump") {
            &["dump"]
        } else {
            &[]
        };

        /// The provenance of this build: the collector of its profile with the code digest of
        /// the workspace.
        pub fn provenance() -> $crate::envelope::Provenance {
            $crate::envelope::Provenance::native(
                $profile,
                (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
                (
                    env!("ARCHKEEL_RUSTC_VERSION"),
                    env!("CARGO_PKG_RUST_VERSION"),
                ),
            )
        }
    };
}
