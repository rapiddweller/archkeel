// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `vtreg`: it runs a registry of a vendored crate.

pub fn run() {
    crate::vtreg_c::make().run_all();
}
