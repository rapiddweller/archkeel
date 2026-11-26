// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnmut`: it drops the value that it gets, and never calls it.

pub fn run() {
    let once: Box<dyn FnOnce()> = crate::fnmut_m::make();
    drop(once);
}
