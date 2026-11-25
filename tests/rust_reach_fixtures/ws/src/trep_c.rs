// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `trep`: it calls a method of a trait of the dependency.

use regdep::Eraser;

pub fn make() -> Box<dyn std::any::Any> {
    regdep::Hold::erase_with(crate::trep_b::X)
}
