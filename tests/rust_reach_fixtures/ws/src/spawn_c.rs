// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `spawn`.

pub fn make() -> Box<dyn Send> {
    Box::new(crate::spawn_b::X)
}
