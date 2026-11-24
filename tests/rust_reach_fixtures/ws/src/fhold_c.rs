// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `fhold`: only a `dyn Sub` here.

pub fn make() -> regdep::Holder {
    regdep::Holder::new(Box::new(crate::fhold_b::X))
}
