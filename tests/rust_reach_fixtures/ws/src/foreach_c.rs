// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `foreach`.

pub fn make() -> Vec<Box<dyn crate::api::Tr>> {
    vec![Box::new(crate::foreach_b::X), Box::new(crate::foreach_b::X)]
}
