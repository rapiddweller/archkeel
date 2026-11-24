// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `hand`: it calls a handle of the workspace that holds an erased pointer.

pub fn run() {
    crate::hand_c::make().go();
}
