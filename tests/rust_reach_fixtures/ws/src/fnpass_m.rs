// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnpass`: a generic function that another module calls coerces the closure of that module.

pub fn make() -> Box<dyn Fn()> {
    let held = crate::fnpass_b::D;
    crate::fnpass_g::pack(move || {
        let _ = &held;
    })
}
