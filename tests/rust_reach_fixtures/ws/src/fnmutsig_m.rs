// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnmutsig`: a closure that holds the type is coerced to `dyn FnMut()` and never made at run time.

pub fn unused() -> Box<dyn FnMut(i64)> {
    let held = crate::fnmutsig_b::D;
    Box::new(move |_| {
        let _ = &held;
    })
}
