// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `panic`: it catches a panic payload and drops it.

pub fn run() {
    let caught = std::panic::catch_unwind(crate::panic_c::boom);
    drop(caught);
}
