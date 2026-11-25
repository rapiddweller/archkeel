// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `vtsend`: it drops a value that a vendored crate erased to `dyn Send`.

pub fn run() {
    drop(crate::vtsend_c::make());
}
