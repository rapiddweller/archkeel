// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `stat`.

pub fn make() -> Box<dyn std::any::Any> {
    regdep::keep_static(crate::stat_b::X)
}
