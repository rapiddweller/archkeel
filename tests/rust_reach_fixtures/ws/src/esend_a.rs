// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `esend`: it drops a `Box<dyn Send>` that a dependency made.

pub fn run() {
    let value = crate::esend_c::make();
    drop(value);
}
