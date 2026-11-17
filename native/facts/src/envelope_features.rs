// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The test features of a linked collector (AD-406).

/// A build with a test feature is refused by `archkeel-collect`.
pub const fn test_features(dump: bool) -> &'static [&'static str] {
    if dump {
        &["dump"]
    } else {
        &[]
    }
}
