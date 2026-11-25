// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `opgen`: it hands an opaque `impl Tr` to the generic function.

use crate::api::Tr;

pub fn make() -> impl Tr {
    crate::opgen_b::X
}

pub fn run() {
    crate::opgen_a::go(make());
}
