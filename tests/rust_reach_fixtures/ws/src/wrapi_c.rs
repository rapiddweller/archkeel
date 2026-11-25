// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `wrapi`: the parameter of the type is unbounded, the bound is on the impl.

use regdep::Erase;

pub fn make() -> Box<dyn std::any::Any> {
    regdep::Wrapper(crate::wrapi_b::X).erase()
}
