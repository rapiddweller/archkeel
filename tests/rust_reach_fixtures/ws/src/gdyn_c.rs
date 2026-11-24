// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `gdyn`: the instance has a `dyn` type argument.

pub fn run() -> usize {
    let boxed: Box<dyn std::fmt::Debug> = Box::new(crate::gdyn_b::X);
    crate::gdyn_a::show(boxed)
}
