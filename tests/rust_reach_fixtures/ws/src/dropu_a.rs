// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `dropu`: foreign code with an unbounded parameter drops the value.

pub fn run() {
    regdep::consume(crate::dropu_b::X);
    std::mem::drop(Some(vec![Box::new(crate::dropu_b::X)]));
}
