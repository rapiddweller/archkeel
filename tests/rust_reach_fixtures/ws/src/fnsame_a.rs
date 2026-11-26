// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnsame`: it drops the value that it gets, and never calls it.

pub fn run() {
    drop(crate::fnsame_n::other());
    drop(crate::fnsame_m::make());
}
