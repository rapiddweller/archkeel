// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnsig`: a closure that holds the type is coerced to `dyn Fn(u8)` and never made at run time.

pub fn unused() -> Box<dyn Fn(i32)> {
    let held = crate::fnsig_b::D;
    Box::new(move |_| {
        let _ = &held;
    })
}
