// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `assoc`: the maker names `dyn Tr` as its associated type.

use crate::api::Tr;

pub struct Maker;

impl crate::assoc_a::Make for Maker {
    type Item = dyn Tr;
    fn make() -> Box<dyn Tr> {
        Box::new(crate::assoc_b::X)
    }
}

pub fn run() {
    crate::assoc_a::run::<Maker>();
}
