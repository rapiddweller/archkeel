// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnonce`: it drops the value that it gets, and never calls it.

pub fn run() {
    let once: Box<dyn FnOnce()> = crate::fnonce_m::make();
    drop(once);
}
