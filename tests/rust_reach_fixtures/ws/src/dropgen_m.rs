// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module of the case `dropgen` that makes and drops a guard.

pub fn run() {
    let _guard = crate::dropgen_a::Guard(crate::dropgen_b::D);
}
