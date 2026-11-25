// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module of the case `cgen` that fixes the type parameter.

pub fn run() {
    crate::cgen_a::outer::<crate::cgen_b::X>();
}
