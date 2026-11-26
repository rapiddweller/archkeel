// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnsame`: two closures with one signature from two modules; one holds the type.

pub fn make() -> Box<dyn Fn()> {
    let held = crate::fnsame_b::D;
    Box::new(move || {
        let _ = &held;
    })
}
