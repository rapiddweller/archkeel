// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `intoc`: foreign code calls the `Into` of a type of `b`.

pub fn run() -> usize {
    regdep::convert(crate::intoc_b::X).len()
}
