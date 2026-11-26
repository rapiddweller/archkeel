// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnhr`: it drops the value that it gets, and never calls it.

pub fn run() {
    let plain: Box<dyn Fn(&'static u8)> = crate::fnhr_m::make();
    drop(plain);
}
