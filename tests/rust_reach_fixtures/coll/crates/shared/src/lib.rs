// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One file, two builds: the member builds it without the feature, the vendored crate `nm` with it.

#[cfg(not(feature = "nm"))]
pub fn member_only() {}

#[cfg(feature = "nm")]
pub fn erase_shared<T: std::any::Any>(value: T) -> Box<dyn std::any::Any> {
    Box::new(value)
}
