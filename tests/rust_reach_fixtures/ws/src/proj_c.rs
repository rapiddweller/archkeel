// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `proj`: the bound is on `I::Item`.

pub fn make() -> Box<dyn std::any::Any> {
    regdep::first_any(vec![crate::proj_b::X].into_iter())
}
