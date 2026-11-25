// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `send`: it drops a `Box<dyn Send>` that a `T: Send` function made.

pub fn run() {
    drop(crate::send_c::make());
}
