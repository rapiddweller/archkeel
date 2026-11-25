// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `autoup`: it drops a `Box<dyn Send>` that was a `Box<dyn Debug + Send>`.

pub fn run() {
    drop(crate::autoup_c::make());
}
