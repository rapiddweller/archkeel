// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `autoup`: the principal trait goes away by an upcast.

pub fn make() -> Box<dyn Send> {
    let value: Box<dyn std::fmt::Debug + Send> = Box::new(crate::autoup_b::X);
    value
}
