// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `gvec`.

pub fn run() -> usize {
    let values: Vec<&dyn std::fmt::Debug> = vec![&crate::gvec_b::X];
    crate::gvec_a::all(&values)
}
