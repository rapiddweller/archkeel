// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `vtblanket`: the trait item is called, and the impl is in the vendored crate.

use vdep::Erase;

pub fn make() -> Box<dyn std::any::Any> {
    crate::vtblanket_b::X.erase()
}
