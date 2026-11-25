// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `princ`: it drops a dependency holder of a `dyn Debug`.

pub fn run() {
    drop(crate::princ_c::make());
}
