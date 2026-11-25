// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `proj`: it drops a `Box<dyn Any>` made from an iterator item.

pub fn run() {
    drop(crate::proj_c::make());
}
