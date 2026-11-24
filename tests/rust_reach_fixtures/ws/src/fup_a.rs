// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fup`: it calls a `Box<dyn Super>` that a dependency upcast from `dyn Sub`.

use regdep::Super;

pub fn run() {
    crate::fup_c::make().hit();
}
