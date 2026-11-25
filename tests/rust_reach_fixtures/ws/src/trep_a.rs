// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `trep`: it drops a `Box<dyn Any>` that the impl of a dependency trait made.

pub fn run() {
    let value = crate::trep_c::make();
    drop(value);
}
