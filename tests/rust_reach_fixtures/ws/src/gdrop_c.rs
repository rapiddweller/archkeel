// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `gdrop`: a non-generic type holds the guard in a field.

pub struct Outer {
    pub guard: crate::gdrop_a::Guard<crate::gdrop_b::D>,
}

pub fn run() {
    drop(Outer {
        guard: crate::gdrop_a::Guard(crate::gdrop_b::D),
    });
}
