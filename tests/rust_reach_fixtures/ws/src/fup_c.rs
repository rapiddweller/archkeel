// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `fup`: the value is only a `dyn Sub` here; the upcast is in the dependency.

pub fn make() -> Box<dyn regdep::Super> {
    regdep::up(Box::new(crate::fup_b::X) as Box<dyn regdep::Sub>)
}
