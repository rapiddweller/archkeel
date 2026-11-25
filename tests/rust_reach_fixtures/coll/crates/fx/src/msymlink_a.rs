// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `msymlink`: it drops a value that a vendored crate with a symbolic link to the root file of a member erased.

pub fn run() {
    drop(crate::msymlink_c::make());
}
