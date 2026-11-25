// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module of the case `closure` that captures the type in a closure.

pub fn make() -> Box<dyn FnOnce()> {
    let held = crate::closure_b::D;
    Box::new(move || {
        let _ = &held;
    })
}
