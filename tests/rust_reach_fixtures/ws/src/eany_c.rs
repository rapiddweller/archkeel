// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `eany`: the dependency erases the type.

pub fn make() -> Box<dyn std::any::Any> {
    regdep::erase_any(crate::eany_b::X)
}
