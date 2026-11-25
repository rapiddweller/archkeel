// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The control `dyn`: it holds a `dyn Tr`, and only the other type is coerced to it.

use crate::api::Tr;

pub fn run() {
    let value: Box<dyn Tr> = Box::new(crate::dyn_c::Z);
    value.hit();
}
