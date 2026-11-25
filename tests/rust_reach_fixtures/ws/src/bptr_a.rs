// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `bptr`: it calls a handle that holds a pointer to bytes, not to `()`.

pub fn run() {
    crate::bptr_c::make().go();
}
