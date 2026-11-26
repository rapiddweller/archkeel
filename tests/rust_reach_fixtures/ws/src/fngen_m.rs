// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fngen`: a generic function coerces its closure to `Box<dyn Fn(T)>`; it has two instances.

pub fn make() -> Box<dyn Fn(u8)> {
    let held = crate::fngen_b::D;
    crate::fngen_g::wrap::<u8>(move |_| {
        let _ = &held;
    })
}

pub fn other() -> Box<dyn Fn(u16)> {
    crate::fngen_g::wrap::<u16>(|_| {})
}
