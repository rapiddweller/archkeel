// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `princ`: the value is a `dyn Debug + Send` here and a `dyn Debug` in the holder.

pub fn make() -> regdep::Slot {
    regdep::Slot::new(Box::new(crate::princ_b::X) as Box<dyn std::fmt::Debug + Send>)
}
