// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `intoraw`.

pub fn leak() -> *mut crate::intoraw_b::X {
    Box::into_raw(Box::new(crate::intoraw_b::X))
}
