// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnonce`: a closure coerced to `Box<dyn Fn()>` is dropped as a `Box<dyn FnOnce()>` (two supertraits up).

pub fn make() -> Box<dyn Fn()> {
    let held = crate::fnonce_b::D;
    Box::new(move || {
        let _ = &held;
    })
}
