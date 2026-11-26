// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnrc`: a closure coerced to `Box<dyn Fn(&u8)>` is dropped as an `Rc<dyn Fn(&u8)>`.

pub fn make() -> Box<dyn Fn(&u8)> {
    let held = crate::fnrc_b::D;
    Box::new(move |_| {
        let _ = &held;
    })
}
