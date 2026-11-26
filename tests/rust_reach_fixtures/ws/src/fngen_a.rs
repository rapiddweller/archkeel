// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fngen`: it drops the value that it gets, and never calls it.

pub fn run() {
    drop(crate::fngen_m::other());
    drop(crate::fngen_m::make());
}
