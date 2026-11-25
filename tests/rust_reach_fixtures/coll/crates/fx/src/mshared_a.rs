// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `mshared`: it drops a value that a vendored crate with the root file of a member erased.

pub fn run() {
    drop(crate::mshared_c::make());
}
