// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `mcoll`: it drops a value that a vendored crate with the package name of a member erased.

pub fn run() {
    drop(crate::mcoll_c::make());
}
