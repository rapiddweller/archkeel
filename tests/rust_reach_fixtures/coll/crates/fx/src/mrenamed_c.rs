// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `mrenamed`.

pub fn make() -> Box<dyn std::any::Any> {
    rn_pkg::erase_any(crate::mrenamed_b::X)
}
