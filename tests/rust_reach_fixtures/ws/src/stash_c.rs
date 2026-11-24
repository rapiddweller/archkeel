// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `stash`.

pub fn make() -> Vec<Box<dyn std::fmt::Debug + Send>> {
    vec![Box::new(crate::stash_b::X)]
}
