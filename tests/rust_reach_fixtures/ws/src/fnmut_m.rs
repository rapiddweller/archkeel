// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnmut`: a closure coerced to `Box<dyn FnMut()>` is dropped as a `Box<dyn FnOnce()>`.

pub fn make() -> Box<dyn FnMut()> {
    let held = crate::fnmut_b::D;
    Box::new(move || {
        let _ = &held;
    })
}
