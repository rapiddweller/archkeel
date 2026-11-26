// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnhr`: a closure coerced to a higher-ranked `dyn Fn`.

pub fn make() -> Box<dyn for<'a> Fn(&'a u8)> {
    let held = crate::fnhr_b::D;
    Box::new(move |_| {
        let _ = &held;
    })
}
