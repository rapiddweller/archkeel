// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `blanket`: a blanket impl names the type of the case as its associated type.

pub struct S;

impl crate::blanket_a::Tag for S {}

impl<T: crate::blanket_a::Tag> crate::blanket_a::Make for T {
    type Item = crate::blanket_b::Y;
    fn make() -> crate::blanket_b::Y {
        crate::blanket_b::Y
    }
}

pub fn run() {
    crate::blanket_a::run::<S>();
}
