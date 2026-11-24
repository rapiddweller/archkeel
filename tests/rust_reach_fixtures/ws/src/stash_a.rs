// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `stash`: it drops a vector of `Box<dyn Debug + Send>`.

pub fn run() {
    drop(crate::stash_c::make());
}
