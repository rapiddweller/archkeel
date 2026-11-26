// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnrc`: it drops the value that it gets, and never calls it.

use std::rc::Rc;

pub fn run() {
    let shared: Rc<dyn Fn(&u8)> = Rc::from(crate::fnrc_m::make());
    drop(shared);
}
