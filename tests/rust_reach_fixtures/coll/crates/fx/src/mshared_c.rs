// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `mshared`.

pub fn make() -> Box<dyn std::any::Any> {
    nm::erase_shared(crate::mshared_b::X)
}
