// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `anybox`.

pub fn make() -> Option<Box<dyn std::any::Any>> {
    Some(Box::new(crate::anybox_b::X))
}
