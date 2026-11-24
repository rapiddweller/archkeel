// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `mcoll`.

pub fn make() -> Box<dyn std::any::Any> {
    vnamed::erase_vendor(crate::mcoll_b::X)
}
