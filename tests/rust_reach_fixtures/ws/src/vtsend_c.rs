// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `vtsend`.

pub fn make() -> Box<dyn Send> {
    vdep::erase_send(crate::vtsend_b::X)
}
