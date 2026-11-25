// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The other type of the control `unbound`, and the code that gives `X` to `std` through an unbounded parameter.

pub struct Z;

pub fn stash() {
    let mut values = Vec::new();
    values.push(crate::unbound_b::X);
    std::mem::forget(values);
}
