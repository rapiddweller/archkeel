// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fhold`: it calls a holder of the dependency that kept an upcast `dyn Super`.

pub fn run() {
    crate::fhold_c::make().run();
}
