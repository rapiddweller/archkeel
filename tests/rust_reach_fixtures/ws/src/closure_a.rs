// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `closure`: it drops a closure that it never calls.

pub fn run() {
    drop(crate::closure_m::make());
}
