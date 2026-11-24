// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `vtreg`: the cast to `dyn Plugin` is in the vendored registry.

pub fn make() -> vdep::Registry {
    let mut registry = vdep::Registry::default();
    registry.register(crate::vtreg_b::B);
    registry
}
