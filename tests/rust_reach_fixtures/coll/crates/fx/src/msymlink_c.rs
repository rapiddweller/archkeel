// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `msymlink`.

pub fn make() -> Box<dyn std::any::Any> {
    nm_sym::erase_shared(crate::msymlink_b::X)
}
