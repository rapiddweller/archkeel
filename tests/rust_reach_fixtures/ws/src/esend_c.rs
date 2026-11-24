// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `esend`: the dependency erases the type.

pub fn make() -> Box<dyn Send> {
    regdep::erase_send(crate::esend_b::X)
}
