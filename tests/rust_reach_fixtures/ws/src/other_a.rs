// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The control `other`: it holds a `dyn Tr`, and the type of `other_b` implements no `Tr`.

use crate::api::Tr;

pub fn run() {
    let value: Box<dyn Tr> = Box::new(crate::other_c::Z);
    value.hit();
}
