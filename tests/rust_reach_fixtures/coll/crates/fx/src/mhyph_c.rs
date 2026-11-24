// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `mhyph`.

pub fn make() -> Box<dyn std::any::Any> {
    b_crate::erase_any(crate::mhyph_b::X)
}
