// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `mhyph`: it drops a value that a hyphenated member erased.

pub fn run() {
    drop(crate::mhyph_c::make());
}
