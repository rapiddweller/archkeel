// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `mcollhy`.

pub fn make() -> Box<dyn std::any::Any> {
    vhy::erase_vendor(crate::mcollhy_b::X)
}
