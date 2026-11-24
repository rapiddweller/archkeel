// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `anybox`: it drops an `Option<Box<dyn Any>>`.

pub fn run() {
    let value = crate::anybox_c::make();
    drop(value);
}
