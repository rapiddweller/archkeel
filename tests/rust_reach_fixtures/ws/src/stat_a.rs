// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `stat`: it drops a `Box<dyn Any>` that a `T: 'static` function made.

pub fn run() {
    drop(crate::stat_c::make());
}
