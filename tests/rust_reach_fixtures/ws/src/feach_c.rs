// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `feach`.

pub fn make() -> Vec<Box<dyn crate::api::Tr>> {
    vec![Box::new(crate::feach_b::X)]
}
