// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `mrenamed`: it drops a value that a member with another directory name erased.

pub fn run() {
    drop(crate::mrenamed_c::make());
}
