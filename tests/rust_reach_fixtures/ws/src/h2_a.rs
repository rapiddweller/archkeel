// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `h2`: it holds a `dyn Plugin` from the registry.

pub fn run() {
    crate::h2_m::put();
    if let Some(plugin) = regdep::take() {
        plugin.hit();
    }
}
