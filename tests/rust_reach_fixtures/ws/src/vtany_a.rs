// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `vtany`: it drops a value that a vendored crate erased to `dyn Any`.

pub fn run() {
    drop(crate::vtany_c::make());
}
