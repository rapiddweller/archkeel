// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `vtblanket`: it drops a value that a blanket impl of a vendored crate erased.

pub fn run() {
    drop(crate::vtblanket_c::make());
}
