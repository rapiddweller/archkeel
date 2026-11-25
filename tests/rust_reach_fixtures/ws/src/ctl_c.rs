// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `ctl`.

pub fn make() -> Box<dyn std::fmt::Debug> {
    Box::new(crate::ctl_b::X)
}
