// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `down`.

pub fn make() -> Box<dyn std::any::Any> {
    Box::new(crate::down_b::X)
}
