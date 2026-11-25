// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `eany`: it drops a `Box<dyn Any>` that a dependency made.

pub fn run() {
    let value = crate::eany_c::make();
    drop(value);
}
