// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `futhold`: it runs a task of the dependency that holds a future.

pub fn run() {
    crate::futhold_c::make().poll_once();
}
