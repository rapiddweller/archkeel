// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `arcfn`: it drops a map of `Arc<dyn Fn>`.

pub fn run() {
    let map = crate::arcfn_c::make();
    drop(map);
}
