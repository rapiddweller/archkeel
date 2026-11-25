// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `deref`: it calls a method through `Deref`.

use crate::api::Tr;

pub fn run() {
    let wrapper = crate::deref_c::W;
    wrapper.hit();
}
