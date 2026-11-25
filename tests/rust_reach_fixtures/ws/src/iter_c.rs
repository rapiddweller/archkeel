// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `iter`: an opaque iterator.

pub fn items() -> impl Iterator<Item = Box<dyn crate::api::Tr>> {
    vec![Box::new(crate::iter_b::X) as Box<dyn crate::api::Tr>].into_iter()
}
